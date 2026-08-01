"""
Job execution: claim jobs from the queue and run them.

  * validate  -> run the submitted bot vs the built-in 'random' opponent in a
                 private match; flip submission to validated/rejected.
  * run_match -> run two active submission bots in a rated match; store the
                 replay, update match result + Glicko-2 ratings.

Bot artifacts are extracted to a temp dir and run as a subprocess
(JSON-line protocol). When USE_NSJAIL=1 the subprocess is wrapped in nsjail
(zero network, time/mem limits).
"""
import json
import os
import secrets
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine", "nexus_wars"))

from config import (SUBMISSIONS_DIR, ENGINE_DIR, ENGINE_VERSION,
                    ACT_TIMEOUT, RUN_TIMEOUT, EPISODE_STEPS, SHIP_SPEED,
                    ENERGY_CAP, ENERGY_REGEN, LAUNCH_ENERGY_COST,
                    USE_NSJAIL, NSJAIL_CFG, MINIO_ENDPOINT)
from db import get_conn, execute, execute_returning, query
from storage import put_json, get_file
import run_match as rm

def rate_elo(r_self, matches_self, r_opp, score):
    # Tie +0 Rule
    if score == 0.5:
        return r_self
    
    # Dynamic K-factor
    k_self = 64.0 if matches_self < 15 else 24.0
    
    # Expected score
    e_self = 1.0 / (1.0 + 10.0 ** ((r_opp - r_self) / 400.0))
    
    # Calculate new rating (cannot go below 0)
    return max(0.0, r_self + k_self * (score - e_self))


def engine_config():
    return {
        "episodeSteps": EPISODE_STEPS,
        "actTimeout": ACT_TIMEOUT,
        "runTimeout": RUN_TIMEOUT,
        "shipSpeed": SHIP_SPEED,
        "energyCap": ENERGY_CAP,
        "energyRegen": ENERGY_REGEN,
        "launchEnergyCost": LAUNCH_ENERGY_COST,
        "seed": None,
    }


def _sandbox_cmd(workdir):
    if not USE_NSJAIL:
        return None
    # We mount the workdir into the jail as read-only /work.
    # The bot command ([sys.executable, entry]) is appended after this.
    return ["nsjail", "-C", NSJAIL_CFG, "-R", f"{workdir}:/work", "--"]


def extract_submission(conn, submission_id):
    """Extract a submission artifact to a temp dir; return the workdir."""
    row = execute_returning(
        conn,
        "SELECT artifact_key FROM submissions WHERE id=%s",
        (submission_id,))
    if not row or not row[0]:
        raise RuntimeError(f"no artifact for submission {submission_id}")
    artifact_key = row[0]
    workdir = tempfile.mkdtemp(prefix=f"bot_{submission_id}_")

    if artifact_key.startswith("submissions/") and MINIO_ENDPOINT:
        ext = os.path.splitext(artifact_key)[1]
        local_path = os.path.join(workdir, f"_artifact{ext}")
        get_file(artifact_key, local_path)
        artifact = local_path
    else:
        artifact = os.path.join(SUBMISSIONS_DIR, artifact_key)

    if artifact.endswith(".py"):
        shutil.copy2(artifact, os.path.join(workdir, "main.py"))
    elif artifact.endswith(".zip"):
        with zipfile.ZipFile(artifact) as z:
            z.extractall(workdir)
    elif artifact.endswith((".tar.gz", ".tgz")):
        with tarfile.open(artifact) as t:
            t.extractall(workdir)
    elif os.path.isdir(artifact):
        shutil.copytree(artifact, workdir, dirs_exist_ok=True)
    else:
        raise RuntimeError(f"unsupported artifact: {artifact}")
    return workdir


def bot_runner(workdir):
    """Build a runner spec for a submission extracted into workdir."""
    entry = os.path.join(workdir, "main.py")
    if not os.path.exists(entry):
        # allow a single .py at any depth
        for root, _, files in os.walk(workdir):
            if "main.py" in files:
                entry = os.path.join(root, "main.py")
                break
        else:
            raise RuntimeError("no main.py found in submission")

    if USE_NSJAIL:
        rel = os.path.relpath(entry, workdir)
        entry = os.path.join("/work", rel).replace("\\", "/")

    command = [sys.executable, entry]
    return {"command": command, "actTimeout": ACT_TIMEOUT, "sandbox": _sandbox_cmd(workdir)}


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
def run_validation(conn, submission_id):
    workdir = extract_submission(conn, submission_id)
    runner_a = rm.make_runner(bot_runner(workdir))
    runner_b = rm.make_runner("random")
    replay = rm.run_match([runner_a, runner_b], engine_config(),
                           seed=secrets.randbits(31))

    key = f"validation/{submission_id}.json"
    size = put_json(key, replay)

    ok = (not runner_a.dead) and replay["info"]["steps"] >= 1
    reason = None if ok else "agent_error_or_timeout"
    execute(conn,
            "UPDATE submissions SET status=%s, validation_replay_key=%s, "
            "reject_reason=%s, engine_version=%s WHERE id=%s",
            ("validated" if ok else "rejected", key, reason, ENGINE_VERSION, submission_id))
    if ok:
        team = execute_returning(conn,
            "SELECT team_id FROM submissions WHERE id=%s", (submission_id,))
        if team:
            execute(conn,
                "INSERT INTO submission_ratings(submission_id, team_id) "
                "VALUES(%s,%s) ON CONFLICT (submission_id) DO NOTHING",
                (submission_id, team[0]))
        promote_submissions(conn, submission_id)
    return ok


def promote_submissions(conn, submission_id):
    """Latest 2 validated submissions by time are 'active'; rest 'inactive'."""
    team = execute_returning(conn, "SELECT team_id FROM submissions WHERE id=%s",
                              (submission_id,))
    if not team:
        return
    team_id = team[0]
    rows = query(conn,
        "SELECT id FROM submissions WHERE team_id=%s "
        "AND status IN ('validated','active','inactive') "
        "ORDER BY created_at DESC", (team_id,))
    ids = [r[0] for r in rows]
    active = set(ids[:2])
    for sid in ids:
        execute(conn, "UPDATE submissions SET status=%s WHERE id=%s",
                ("active" if sid in active else "inactive", sid))


# --------------------------------------------------------------------------
# Rated match
# --------------------------------------------------------------------------
def run_rated(conn, match_id):
    m = execute_returning(conn,
        "SELECT id, seed, team_a_id, team_b_id, submission_a_id, "
        "submission_b_id, configuration_json FROM matches WHERE id=%s",
        (match_id,))
    (mid, seed, ta, tb, sa, sb, cfg_json) = m
    cfg = dict(engine_config())
    if cfg_json:
        cfg.update(cfg_json)

    wa = extract_submission(conn, sa)
    wb = extract_submission(conn, sb)
    runner_a = rm.make_runner(bot_runner(wa))
    runner_b = rm.make_runner(bot_runner(wb))

    replay = rm.run_match([runner_a, runner_b], cfg, seed=seed)

    key = f"rated/{match_id}.json"
    size = put_json(key, replay)

    winner = replay["info"]["winner"]
    win_code = "a" if winner == 0 else ("b" if winner == 1 else "draw")
    execute(conn,
            "UPDATE matches SET status='finished', winner=%s, reason=%s, "
            "replay_key=%s, scores=%s, finished_at=now(), duration_ms=%s "
            "WHERE id=%s",
            (win_code, replay["info"]["reason"], key,
             json.dumps(replay["info"]["scores"]), replay["info"]["durationMs"], match_id))

    update_ratings(conn, ta, tb, winner, mid, sa, sb)
    return win_code


def update_ratings(conn, team_a, team_b, winner, match_id, sub_a, sub_b):
    already_rated = execute_returning(conn,
        "SELECT 1 FROM match_participants WHERE match_id=%s LIMIT 1", (match_id,))
    if already_rated:
        return

    now = datetime.now(timezone.utc)
    is_draw = (winner != 0 and winner != 1)

    # Update team ratings for backwards-compatible leaderboard
    def load_team(tid):
        r = execute_returning(conn,
            "SELECT rating, rd, volatility, last_match_at, matches_played, "
            "wins, losses, draws FROM ratings WHERE team_id=%s FOR UPDATE", (tid,))
        if not r:
            execute(conn,
                    "INSERT INTO ratings(team_id) VALUES(%s) "
                    "ON CONFLICT (team_id) DO NOTHING", (tid,))
            r = execute_returning(conn,
                "SELECT rating, rd, volatility, last_match_at, matches_played, "
                "wins, losses, draws FROM ratings WHERE team_id=%s FOR UPDATE", (tid,))
        return r

    ra = load_team(team_a)
    rb = load_team(team_b)

    score_a = 1.0 if winner == 0 else (0.0 if winner == 1 else 0.5)
    score_b = 1.0 if winner == 1 else (0.0 if winner == 0 else 0.5)

    na_r = rate_elo(ra[0], ra[4], rb[0], score_a)
    nb_r = rate_elo(rb[0], rb[4], ra[0], score_b)

    execute(conn,
            "UPDATE ratings SET rating=%s, rd=%s, volatility=%s, last_match_at=%s, "
            "matches_played=matches_played+1, wins=wins+%s, losses=losses+%s, "
            "draws=draws+%s WHERE team_id=%s",
            (na_r, ra[1], ra[2], now,
             1 if winner == 0 else 0, 1 if winner == 1 else 0,
             1 if is_draw else 0, team_a))
    execute(conn,
            "UPDATE ratings SET rating=%s, rd=%s, volatility=%s, last_match_at=%s, "
            "matches_played=matches_played+1, wins=wins+%s, losses=losses+%s, "
            "draws=draws+%s WHERE team_id=%s",
            (nb_r, rb[1], rb[2], now,
             1 if winner == 1 else 0, 1 if winner == 0 else 0,
             1 if is_draw else 0, team_b))

    # Update per-submission ratings
    def load_sub(sub_id):
        return execute_returning(conn,
            "SELECT rating, rd, volatility, last_match_at, matches_played, "
            "wins, losses, draws FROM submission_ratings "
            "WHERE submission_id=%s FOR UPDATE", (sub_id,))

    sa = load_sub(sub_a)
    sb = load_sub(sub_b)

    def ensure_sub(sub_id, tid):
        r = execute_returning(conn,
            "SELECT rating, rd, volatility, last_match_at, matches_played, "
            "wins, losses, draws FROM submission_ratings "
            "WHERE submission_id=%s FOR UPDATE", (sub_id,))
        if not r:
            execute(conn,
                "INSERT INTO submission_ratings(submission_id, team_id) "
                "VALUES(%s,%s)", (sub_id, tid))
            r = execute_returning(conn,
                "SELECT rating, rd, volatility, last_match_at, matches_played, "
                "wins, losses, draws FROM submission_ratings "
                "WHERE submission_id=%s FOR UPDATE", (sub_id,))
        return r

    if not sa:
        sa = ensure_sub(sub_a, team_a)
    if not sb:
        sb = ensure_sub(sub_b, team_b)

    nsa_r = rate_elo(sa[0], sa[4], sb[0], score_a)
    nsb_r = rate_elo(sb[0], sb[4], sa[0], score_b)

    execute(conn,
            "UPDATE submission_ratings SET rating=%s, rd=%s, volatility=%s, "
            "last_match_at=%s, matches_played=matches_played+1, "
            "wins=wins+%s, losses=losses+%s, draws=draws+%s "
            "WHERE submission_id=%s",
            (nsa_r, sa[1], sa[2], now,
             1 if winner == 0 else 0, 1 if winner == 1 else 0,
             1 if is_draw else 0, sub_a))
    execute(conn,
            "UPDATE submission_ratings SET rating=%s, rd=%s, volatility=%s, "
            "last_match_at=%s, matches_played=matches_played+1, "
            "wins=wins+%s, losses=losses+%s, draws=draws+%s "
            "WHERE submission_id=%s",
            (nsb_r, sb[1], sb[2], now,
             1 if winner == 1 else 0, 1 if winner == 0 else 0,
             1 if is_draw else 0, sub_b))

    for idx, (tid, sub, r_before, r_after, rd_after) in enumerate([
        (team_a, sub_a, ra[0], na_r, ra[1]),
        (team_b, sub_b, rb[0], nb_r, rb[1]),
    ]):
        execute(conn,
                "INSERT INTO match_participants(match_id, team_id, player_index, "
                "submission_id, rating_before, rd_before, rating_after, rd_after) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (match_id, team_id) DO UPDATE SET "
                "rating_after=EXCLUDED.rating_after, rd_after=EXCLUDED.rd_after",
                (match_id, tid, idx, sub, r_before,
                 ra[1] if idx == 0 else rb[1], r_after, rd_after))


# --------------------------------------------------------------------------
# Dispatch
# --------------------------------------------------------------------------
def run_job(job):
    conn = get_conn()
    try:
        jtype = job[1]
        payload = job[2] if isinstance(job[2], dict) else json.loads(job[2])
        if jtype == "validate":
            run_validation(conn, payload["submission_id"])
        elif jtype == "run_match":
            run_rated(conn, payload["match_id"])
        else:
            raise RuntimeError(f"unknown job type {jtype}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

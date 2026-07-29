"""
Ladder matchmaker (Orbit Wars style).

Each team may have up to 2 active submissions. The matchmaker picks the *newest*
active submission per team, pairs teams by Glicko-2 rating proximity, and enqueues
rated matches. A team fights at most ONE match at a time — if a team already has
a pending/running match it is skipped.

Key properties (inspired by Orbit Wars / Kaggle sim-comps):
  - Advisory lock prevents concurrent matchmaker runs across worker instances.
  - Newer teams (fewer matches played) are matched first so they get rapid feedback.
  - Fixed cooldown window prevents the same two teams from being rematched too soon.
  - Rating gap ceiling keeps matches competitive.
  - Exactly one submission per team per match cycle (the newest active one).
  - Each team participates in at most one match per cycle (used_teams guard).
"""
import json
import os
import secrets
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine", "nexus_wars"))

from db import get_conn, execute, execute_returning, query
from jobs import engine_config

MATCHMAKER_LOCK = 87349201
MAX_RATING_GAP = 400
TEAM_COOLDOWN_MINUTES = 1
PAIR_COOLDOWN_MINUTES = 8
MAX_MATCHES_PER_CYCLE = 8


def _acquire_lock(conn):
    """Acquire a session-level advisory lock so only one matchmaker runs."""
    execute(conn, "SELECT pg_advisory_lock(%s)", (MATCHMAKER_LOCK,))


def _release_lock(conn):
    execute(conn, "SELECT pg_advisory_unlock(%s)", (MATCHMAKER_LOCK,))


def _recently_matched(conn, ta, tb):
    # Rematch window: if either team has a newer active submission than their
    # last match, allow rematch (the bot changed, so the matchup is new).
    for team_id, other_id in [(ta, tb), (tb, ta)]:
        newest = execute_returning(conn,
            "SELECT created_at FROM submissions "
            "WHERE team_id=%s AND status='active' "
            "ORDER BY created_at DESC LIMIT 1",
            (team_id,))
        if not newest or not newest[0]:
            continue
        last_match = execute_returning(conn,
            "SELECT MAX(finished_at) FROM matches "
            "WHERE ((team_a_id=%s AND team_b_id=%s) OR "
            "       (team_a_id=%s AND team_b_id=%s)) "
            "  AND status='finished'",
            (ta, tb, tb, ta))
        if last_match and last_match[0] and newest[0] > last_match[0]:
            return False  # newer submission than last match -> allow rematch

    # Fall back to fixed cooldown window based on finished_at to avoid rapid repeat pairings
    rows = execute_returning(conn,
        "SELECT 1 FROM matches "
        "WHERE ((team_a_id=%s AND team_b_id=%s) OR (team_a_id=%s AND team_b_id=%s)) "
        "AND status='finished' "
        "AND finished_at > now() - (%s::text || ' minutes')::interval LIMIT 1",
        (ta, tb, tb, ta, PAIR_COOLDOWN_MINUTES))
    return bool(rows)


def _has_pending_match(conn, submission_id):
    rows = execute_returning(conn,
        "SELECT 1 FROM matches "
        "WHERE (submission_a_id=%s OR submission_b_id=%s) "
        "AND status IN ('pending', 'running') "
        "LIMIT 1",
        (submission_id, submission_id))
    return bool(rows)


def _in_cooldown(conn, team_id):
    """True if the team finished a match within TEAM_COOLDOWN_MINUTES."""
    rows = execute_returning(conn,
        "SELECT 1 FROM matches "
        "WHERE (team_a_id=%s OR team_b_id=%s) "
        "AND status = 'finished' "
        "AND finished_at > now() - (%s::text || ' minutes')::interval "
        "LIMIT 1",
        (team_id, team_id, TEAM_COOLDOWN_MINUTES))
    return bool(rows)


def create_match(conn, a, b):
    """a/b are (team_id, submission_id). Creates match + job row."""
    seed = secrets.randbits(31)
    mid = execute_returning(conn,
        "INSERT INTO matches(team_a_id, team_b_id, submission_a_id, "
        "submission_b_id, seed, status, configuration_json, kind) "
        "VALUES(%s,%s,%s,%s,%s,'pending',%s,'rated') RETURNING id",
        (a[0], b[0], a[1], b[1], seed, json.dumps(engine_config())))
    match_id = str(mid[0])
    execute(conn,
            "INSERT INTO jobs(type, payload_json, status) "
            "VALUES('run_match', %s, 'pending')",
            (json.dumps({"match_id": match_id}),))
    return match_id


def _reap_stuck_jobs(conn):
    """Clean up jobs and matches stuck in 'running' or 'pending' for > 12 minutes (e.g. worker crash)."""
    execute(conn,
        "UPDATE jobs SET status='failed', error='worker_timeout', finished_at=now() "
        "WHERE status='running' AND started_at < now() - interval '12 minutes'")
    execute(conn,
        "UPDATE matches SET status='errored', reason='worker_timeout', finished_at=now() "
        "WHERE status IN ('pending','running') AND created_at < now() - interval '12 minutes'")


def enqueue_matches(conn, limit=MAX_MATCHES_PER_CYCLE):
    _acquire_lock(conn)
    try:
        return _enqueue_locked(conn, limit)
    except Exception:
        conn.rollback()
        raise
    finally:
        _release_lock(conn)


def _enqueue_locked(conn, limit):
    _reap_stuck_jobs(conn)

    rows = query(conn,
        "SELECT s.team_id, s.id, COALESCE(sr.rating, 600.0), "
        "  COALESCE(sr.matches_played, 0) "
        "FROM submissions s "
        "LEFT JOIN submission_ratings sr ON sr.submission_id = s.id "
        "WHERE s.status = 'active' "
        "ORDER BY s.team_id, s.created_at DESC", ())

    # Deduplicate: keep only the newest active submission per team.
    # The query is already ordered by team_id, created_at DESC so the first
    # row for each team_id is the newest one.
    seen_teams: set = set()
    entries = []
    for r in rows:
        tid = r[0]
        if tid in seen_teams:
            continue
        seen_teams.add(tid)
        entries.append((tid, r[1], float(r[2]), int(r[3])))

    # 1. Filter: remove submissions with pending/running matches or team in cooldown.
    eligible = []
    for tid, sid, rating, played in entries:
        if _has_pending_match(conn, sid):
            continue
        if _in_cooldown(conn, tid):
            continue
        eligible.append((tid, sid, rating, played))

    # 2. Sort: fewer matches played first (new teams get rapid feedback),
    #    break ties by lower rating (so newcomers meet near-peer opponents).
    eligible.sort(key=lambda x: (x[3], x[2]))

    # 3. Dynamic limit scaling & Greedy best-fit pairing.
    #    Each team participates in at most one match per cycle (enforced by used_teams).
    effective_limit = min(limit, max(1, len(eligible) // 2))
    created = 0
    used_subs: set = set()
    used_teams: set = set()
    for i in range(len(eligible)):
        if created >= effective_limit:
            break
        tid_a, sid_a, rating_a, played_a = eligible[i]
        if tid_a in used_teams or sid_a in used_subs:
            continue
        best = None
        best_gap = None
        for j in range(i + 1, len(eligible)):
            tid_b, sid_b, rating_b, played_b = eligible[j]
            if tid_b in used_teams or sid_b in used_subs:
                continue
            if tid_a == tid_b:
                continue  # same team — each team has exactly one entry now
            if _recently_matched(conn, tid_a, tid_b):
                continue
            gap = abs(rating_a - rating_b)
            if gap > MAX_RATING_GAP:
                continue
            if best is None or gap < best_gap:
                best = j
                best_gap = gap
        if best is not None:
            tid_b, sid_b, rating_b, played_b = eligible[best]
            create_match(conn, (tid_a, sid_a), (tid_b, sid_b))
            used_subs.update({sid_a, sid_b})
            used_teams.update({tid_a, tid_b})
            created += 1

    conn.commit()
    return created


def main():
    conn = get_conn()
    try:
        n = enqueue_matches(conn)
        print(f"matchmaker enqueued {n} matches")
    finally:
        conn.close()


if __name__ == "__main__":
    main()

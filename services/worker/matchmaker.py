import json
import os
import secrets
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine", "nexus_wars"))

from db import get_conn, execute, execute_returning, query
from jobs import engine_config

MATCHMAKER_LOCK = 87349201
MAX_PER_TEAM_PER_HOUR_MIN = 4
RATING_GAP_SOFT_FACTOR = 0.40
RATING_GAP_HARD_FACTOR = 0.70
RECENCY_PENALTY_BASE = 10.0
LOAD_PENALTY_BASE = 3.0


def _acquire_lock(conn):
    """Acquire a session-level advisory lock so only one matchmaker runs."""
    execute(conn, "SELECT pg_advisory_lock(%s)", (MATCHMAKER_LOCK,))


def _release_lock(conn):
    execute(conn, "SELECT pg_advisory_unlock(%s)", (MATCHMAKER_LOCK,))


def _compute_dynamic_params(n_teams, rating_spread):
    """All matchmaking thresholds derived from live leaderboard state."""
    pair_cooldown = max(6, min(25, n_teams * 4))
    agent_cooldown = max(3, min(15, n_teams * 2))
    soft_gap = max(100.0, rating_spread * RATING_GAP_SOFT_FACTOR)
    hard_gap = max(200.0, rating_spread * RATING_GAP_HARD_FACTOR)
    per_team_hourly_cap = max(MAX_PER_TEAM_PER_HOUR_MIN, 60 // max(1, n_teams))
    matches_per_cycle = max(4, n_teams // 2)
    return pair_cooldown, agent_cooldown, soft_gap, hard_gap, per_team_hourly_cap, matches_per_cycle


def _recently_matched(conn, ta, tb, pair_cooldown_min=15):
    if ta == tb:
        # For self-pairing of distinct submissions, allow rematch every 3 minutes (intended)
        rows = execute_returning(conn,
            "SELECT 1 FROM matches "
            "WHERE team_a_id=%s AND team_b_id=%s AND status='finished' "
            "AND finished_at > now() - interval '3 minutes' LIMIT 1",
            (ta, tb))
        return bool(rows)

    # Rematch window: if either team has a newer active submission than their
    # last match, allow rematch immediately (the bot changed).
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

    # Fall back to dynamic pair cooldown window based on finished_at
    rows = execute_returning(conn,
        "SELECT 1 FROM matches "
        "WHERE ((team_a_id=%s AND team_b_id=%s) OR (team_a_id=%s AND team_b_id=%s)) "
        "AND status='finished' "
        "AND finished_at > now() - (%s::text || ' minutes')::interval LIMIT 1",
        (ta, tb, tb, ta, str(pair_cooldown_min)))
    return bool(rows)


def _has_pending_match(conn, submission_id):
    rows = execute_returning(conn,
        "SELECT 1 FROM matches "
        "WHERE (submission_a_id=%s OR submission_b_id=%s) "
        "AND status IN ('pending', 'running') "
        "LIMIT 1",
        (submission_id, submission_id))
    return bool(rows)


def _in_cooldown(conn, submission_id, agent_cooldown_min=5):
    """True if this specific agent/submission finished a match within agent_cooldown_min."""
    rows = execute_returning(conn,
        "SELECT 1 FROM matches "
        "WHERE (submission_a_id=%s OR submission_b_id=%s) "
        "AND status = 'finished' "
        "AND finished_at > now() - (%s::text || ' minutes')::interval "
        "LIMIT 1",
        (submission_id, submission_id, str(agent_cooldown_min)))
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


def enqueue_matches(conn, limit=None):
    _acquire_lock(conn)
    try:
        return _enqueue_locked(conn, limit)
    except Exception:
        conn.rollback()
        raise
    finally:
        _release_lock(conn)


def _enqueue_locked(conn, limit_override=None):
    _reap_stuck_jobs(conn)

    rows = query(conn,
        "SELECT s.team_id, s.id, COALESCE(sr.rating, 600.0), "
        "  COALESCE(sr.matches_played, 0), COALESCE(sr.rd, 350.0) "
        "FROM submissions s "
        "LEFT JOIN submission_ratings sr ON sr.submission_id = s.id "
        "WHERE s.status = 'active' "
        "ORDER BY s.created_at DESC", ())

    if not rows:
        return 0

    unique_teams = {r[0] for r in rows}
    n_teams = len(unique_teams)

    ratings = [float(r[2]) for r in rows]
    rating_spread = (max(ratings) - min(ratings)) if ratings else 0.0

    (pair_cooldown, agent_cooldown, soft_gap, hard_gap,
     per_team_hourly_cap, matches_per_cycle) = _compute_dynamic_params(n_teams, rating_spread)

    limit = limit_override if limit_override is not None else matches_per_cycle

    # Query hourly match counts per team
    recent_rows = query(conn,
        "SELECT tid, COUNT(*) FROM ("
        "  SELECT team_a_id AS tid FROM matches WHERE finished_at > now() - interval '60 minutes' AND status='finished'"
        "  UNION ALL "
        "  SELECT team_b_id AS tid FROM matches WHERE finished_at > now() - interval '60 minutes' AND status='finished'"
        ") t GROUP BY tid", ())
    team_hour_counts = {r[0]: int(r[1]) for r in recent_rows}
    avg_hour_matches = (sum(team_hour_counts.values()) / max(1, len(team_hour_counts))) if team_hour_counts else 0.0

    # Query last match time between pairs (in minutes ago)
    pair_rows = query(conn,
        "SELECT team_a_id, team_b_id, EXTRACT(EPOCH FROM (now() - MAX(finished_at))) / 60.0 "
        "FROM matches WHERE status='finished' GROUP BY team_a_id, team_b_id", ())
    pair_last_played = {}
    for r in pair_rows:
        ta, tb, mins = r[0], r[1], float(r[2]) if r[2] is not None else 999999.0
        pair_last_played[(ta, tb)] = min(pair_last_played.get((ta, tb), mins), mins)
        pair_last_played[(tb, ta)] = min(pair_last_played.get((tb, ta), mins), mins)

    # Query last match time per team (in minutes ago)
    team_last_rows = query(conn,
        "SELECT tid, EXTRACT(EPOCH FROM (now() - MAX(finished_at))) / 60.0 "
        "FROM ("
        "  SELECT team_a_id AS tid, finished_at FROM matches WHERE status='finished'"
        "  UNION ALL "
        "  SELECT team_b_id AS tid, finished_at FROM matches WHERE status='finished'"
        ") t GROUP BY tid", ())
    team_last_match = {r[0]: float(r[1]) if r[1] is not None else 999999.0 for r in team_last_rows}

    # 1. Filter: remove submissions with pending/running matches or agent in cooldown.
    eligible = []
    for r in rows:
        tid, sid, rating, played, rd = r[0], r[1], float(r[2]), int(r[3]), float(r[4])
        if _has_pending_match(conn, sid):
            continue
        if _in_cooldown(conn, sid, agent_cooldown):
            continue
        eligible.append((tid, sid, rating, played, rd))

    if not eligible:
        return 0

    created = 0
    used_subs: set = set()
    used_teams: set = set()

    def find_and_create_pairs(current_hard_gap, current_pair_cooldown):
        nonlocal created
        candidates = []
        for i in range(len(eligible)):
            tid_a, sid_a, rating_a, played_a, rd_a = eligible[i]
            for j in range(i + 1, len(eligible)):
                tid_b, sid_b, rating_b, played_b, rd_b = eligible[j]
                if tid_a == tid_b:
                    continue

                if _recently_matched(conn, tid_a, tid_b, current_pair_cooldown):
                    continue

                h_count_a = team_hour_counts.get(tid_a, 0)
                h_count_b = team_hour_counts.get(tid_b, 0)
                mins_a = team_last_match.get(tid_a, 999999.0)
                mins_b = team_last_match.get(tid_b, 999999.0)

                is_starved_a = (h_count_a == 0) or (mins_a > 45.0)
                is_starved_b = (h_count_b == 0) or (mins_b > 45.0)

                gap = abs(rating_a - rating_b)
                # Bypass hard gap if either team is starved to guarantee at least 1 match/hour
                if gap > current_hard_gap and not (is_starved_a or is_starved_b):
                    continue

                if h_count_a >= per_team_hourly_cap and h_count_b >= per_team_hourly_cap:
                    continue

                # Penalty score calculation
                norm_gap = gap / max(1.0, rating_spread)
                mins_ago = pair_last_played.get((tid_a, tid_b), 999999.0)
                recency = RECENCY_PENALTY_BASE * max(0.0, 1.0 - (mins_ago / max(1.0, float(current_pair_cooldown))))
                overload = (max(0, h_count_a - avg_hour_matches) + max(0, h_count_b - avg_hour_matches))
                load_penalty = LOAD_PENALTY_BASE * overload

                # Information Gain Bonus: uncalibrated bots (high RD) get matching priority to calibrate faster
                info_gain_bonus = 0.4 * ((rd_a + rd_b) / 700.0)

                # Anti-Starvation Aging Boost: teams waiting >30m accumulate priority discount
                starve_a = max(0.0, (mins_a - 30.0) / 15.0) if (h_count_a == 0 or mins_a > 30.0) else 0.0
                starve_b = max(0.0, (mins_b - 30.0) / 15.0) if (h_count_b == 0 or mins_b > 30.0) else 0.0
                starvation_boost = 15.0 * (starve_a + starve_b)

                cost = norm_gap + recency + load_penalty - info_gain_bonus - starvation_boost
                candidates.append((cost, i, j))

        candidates.sort(key=lambda x: x[0])

        for cost, i, j in candidates:
            if created >= limit:
                break
            tid_a, sid_a, _, _, _ = eligible[i]
            tid_b, sid_b, _, _, _ = eligible[j]
            if tid_a in used_teams or tid_b in used_teams or sid_a in used_subs or sid_b in used_subs:
                continue
            create_match(conn, (tid_a, sid_a), (tid_b, sid_b))
            used_subs.update({sid_a, sid_b})
            used_teams.update({tid_a, tid_b})
            created += 1

    # Pass 1: Standard matching with dynamic parameters
    find_and_create_pairs(hard_gap, pair_cooldown)

    # Pass 1b: Fallback relaxation if no matches were created (e.g. low pool activity)
    if created == 0 and len(unique_teams) >= 2:
        find_and_create_pairs(hard_gap * 1.5, max(3.0, pair_cooldown * 0.5))

    # Pass 2: Fallback self-pairing for teams with multiple active submissions if no opponent team available
    if created < limit and len(unique_teams) < 2:
        for i in range(len(eligible)):
            if created >= limit:
                break
            tid_a, sid_a, rating_a, played_a, rd_a = eligible[i]
            if sid_a in used_subs:
                continue
            for j in range(i + 1, len(eligible)):
                tid_b, sid_b, rating_b, played_b, rd_b = eligible[j]
                if sid_b in used_subs or sid_a == sid_b:
                    continue
                if _recently_matched(conn, tid_a, tid_b, pair_cooldown):
                    continue
                create_match(conn, (tid_a, sid_a), (tid_b, sid_b))
                used_subs.update({sid_a, sid_b})
                created += 1
                break

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


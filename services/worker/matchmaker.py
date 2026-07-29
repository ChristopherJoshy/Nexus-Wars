"""
Ladder matchmaker (Orbit Wars style).

Each team may have up to 2 active submissions. The matchmaker pairs submissions
by Glicko-2 rating proximity and enqueues rated matches.

Key properties:
  - Advisory lock prevents concurrent matchmaker runs across worker instances.
  - Newer submissions / teams (fewer matches played) are matched first for rapid feedback.
  - Short team cooldown (10s) prevents thread contention while enabling frequent play.
  - Dynamic pair cooldown (30s for small pools <=3 teams, 2m for larger pools).
  - Immediate rematch bypass whenever a new agent submission is added.
  - Primary pairing across distinct teams; fallback self-pairing across distinct active submissions.
"""
import json
import os
import secrets
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine", "nexus_wars"))

from db import get_conn, execute, execute_returning, query
from jobs import engine_config

MATCHMAKER_LOCK = 87349201
MAX_RATING_GAP = 500
TEAM_COOLDOWN_SECONDS = 10
MAX_MATCHES_PER_CYCLE = 8


def _acquire_lock(conn):
    """Acquire a session-level advisory lock so only one matchmaker runs."""
    execute(conn, "SELECT pg_advisory_lock(%s)", (MATCHMAKER_LOCK,))


def _release_lock(conn):
    execute(conn, "SELECT pg_advisory_unlock(%s)", (MATCHMAKER_LOCK,))


def _recently_matched(conn, ta, tb, pair_cooldown_min=1.0):
    if ta == tb:
        # For self-pairing of distinct submissions, allow rematch every 30s
        rows = execute_returning(conn,
            "SELECT 1 FROM matches "
            "WHERE team_a_id=%s AND team_b_id=%s AND status='finished' "
            "AND finished_at > now() - interval '30 seconds' LIMIT 1",
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


def _in_cooldown(conn, team_id):
    """True if the team finished a match within TEAM_COOLDOWN_SECONDS (10s)."""
    rows = execute_returning(conn,
        "SELECT 1 FROM matches "
        "WHERE (team_a_id=%s OR team_b_id=%s) "
        "AND status = 'finished' "
        "AND finished_at > now() - (%s::text || ' seconds')::interval "
        "LIMIT 1",
        (team_id, team_id, str(TEAM_COOLDOWN_SECONDS)))
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
        "ORDER BY s.created_at DESC", ())

    if not rows:
        return 0

    unique_teams = {r[0] for r in rows}
    pair_cooldown_min = 0.5 if len(unique_teams) <= 3 else 2.0

    # 1. Filter: remove submissions with pending/running matches or team in cooldown.
    eligible = []
    for r in rows:
        tid, sid, rating, played = r[0], r[1], float(r[2]), int(r[3])
        if _has_pending_match(conn, sid):
            continue
        if _in_cooldown(conn, tid):
            continue
        eligible.append((tid, sid, rating, played))

    # Sort: fewer matches played first for rapid feedback, then lower rating.
    eligible.sort(key=lambda x: (x[3], x[2]))

    created = 0
    used_subs: set = set()
    used_teams: set = set()

    # Pass 1: Pair distinct teams
    for i in range(len(eligible)):
        if created >= limit:
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
                continue  # distinct teams only in pass 1
            if _recently_matched(conn, tid_a, tid_b, pair_cooldown_min):
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

    # Pass 2: Fallback self-pairing for teams with multiple active submissions if no opponent team available
    if created < limit and len(unique_teams) < 2:
        for i in range(len(eligible)):
            if created >= limit:
                break
            tid_a, sid_a, rating_a, played_a = eligible[i]
            if sid_a in used_subs:
                continue
            for j in range(i + 1, len(eligible)):
                tid_b, sid_b, rating_b, played_b = eligible[j]
                if sid_b in used_subs or sid_a == sid_b:
                    continue
                if _recently_matched(conn, tid_a, tid_b, pair_cooldown_min):
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

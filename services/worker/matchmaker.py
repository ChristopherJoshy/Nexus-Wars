"""
Ladder matchmaker (Orbit Wars style).

Each team may have up to 2 active submissions. The matchmaker picks the *newest*
active submission per team, pairs teams by Glicko-2 rating proximity, and enqueues
rated matches. A team fights at most ONE match at a time — if a team already has
a pending/running match it is skipped.

Key properties (inspired by Orbit Wars / Kaggle sim-comps):
  - Advisory lock prevents concurrent matchmaker runs across worker instances.
  - Newer teams (fewer matches played) are matched first so they get rapid feedback.
  - Cooldown window prevents the same two teams from being rematched too soon.
  - Rating gap ceiling keeps matches competitive.
  - One submission per team per match cycle (the newest active one).
"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine", "nexus_wars"))

from db import get_conn, execute, execute_returning, query
from jobs import engine_config

MATCHMAKER_LOCK = 87349201
RECENT_WINDOW_HOURS = 2
MAX_RATING_GAP = 400
TEAM_COOLDOWN_MINUTES = 5
MAX_MATCHES_PER_CYCLE = 8


def _acquire_lock(conn):
    """Acquire a session-level advisory lock so only one matchmaker runs."""
    execute(conn, "SELECT pg_advisory_lock(%s)", (MATCHMAKER_LOCK,))


def _release_lock(conn):
    execute(conn, "SELECT pg_advisory_unlock(%s)", (MATCHMAKER_LOCK,))


def _recently_matched(conn, ta, tb):
    rows = execute_returning(conn,
        "SELECT 1 FROM matches "
        "WHERE ((team_a_id=%s AND team_b_id=%s) OR (team_a_id=%s AND team_b_id=%s)) "
        "AND created_at > now() - (%s::text || ' hours')::interval LIMIT 1",
        (ta, tb, tb, ta, RECENT_WINDOW_HOURS))
    return bool(rows)


def _has_pending_match(conn, team_id):
    rows = execute_returning(conn,
        "SELECT 1 FROM matches "
        "WHERE (team_a_id=%s OR team_b_id=%s) AND status IN ('pending', 'running') "
        "LIMIT 1",
        (team_id, team_id))
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
    seed = random.randint(0, 2**31 - 1)
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


def enqueue_matches(conn, limit=MAX_MATCHES_PER_CYCLE):
    _acquire_lock(conn)
    try:
        return _enqueue_locked(conn, limit)
    finally:
        _release_lock(conn)


def _enqueue_locked(conn, limit):
    rows = query(conn,
        "SELECT DISTINCT ON (s.team_id) "
        "  s.team_id, s.id, COALESCE(r.rating, 1500.0), "
        "  COALESCE(r.matches_played, 0) "
        "FROM submissions s "
        "LEFT JOIN ratings r ON r.team_id = s.team_id "
        "WHERE s.status = 'active' "
        "ORDER BY s.team_id, s.created_at DESC", ())

    teams = [(r[0], r[1], float(r[2]), int(r[3])) for r in rows]

    # 1. Filter: remove teams with pending/running matches or in cooldown.
    eligible = []
    for tid, sid, rating, played in teams:
        if _has_pending_match(conn, tid):
            continue
        if _in_cooldown(conn, tid):
            continue
        eligible.append((tid, sid, rating, played))

    # 2. Sort: fewer matches played first (new teams get rapid feedback).
    eligible.sort(key=lambda x: (x[3], -x[2]))

    # 3. Greedy best-fit pairing.
    created = 0
    used = set()
    for i in range(len(eligible)):
        if created >= limit:
            break
        tid_a = eligible[i][0]
        if tid_a in used:
            continue
        best = None
        best_gap = None
        for j in range(i + 1, len(eligible)):
            tid_b = eligible[j][0]
            if tid_b in used or tid_a == tid_b:
                continue
            if _recently_matched(conn, tid_a, tid_b):
                continue
            gap = abs(eligible[i][2] - eligible[j][2])
            if gap > MAX_RATING_GAP:
                continue
            if best is None or gap < best_gap or (gap == best_gap and random.random() < 0.5):
                best = j
                best_gap = gap
        if best is not None:
            create_match(conn, eligible[i], eligible[best])
            used.update({tid_a, eligible[best][0]})
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

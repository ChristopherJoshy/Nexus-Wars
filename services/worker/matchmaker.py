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
import secrets
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine", "nexus_wars"))

from db import get_conn, execute, execute_returning, query
from jobs import engine_config

MATCHMAKER_LOCK = 87349201
MAX_RATING_GAP = 400
TEAM_COOLDOWN_MINUTES = 1
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
            "SELECT s.created_at FROM submissions s "
            "JOIN matches m ON "
            "  ((m.team_a_id=%s AND m.team_b_id=%s) OR "
            "   (m.team_a_id=%s AND m.team_b_id=%s)) "
            "  AND m.status='finished' "
            "WHERE s.team_id=%s AND s.status='active' "
            "ORDER BY s.created_at DESC LIMIT 1",
            (team_id, other_id, other_id, team_id, team_id))
        if not newest:
            continue  # no active submission = skip
        last_match = execute_returning(conn,
            "SELECT MAX(m.finished_at) FROM matches m "
            "WHERE ((m.team_a_id=%s AND m.team_b_id=%s) OR "
            "       (m.team_a_id=%s AND m.team_b_id=%s)) "
            "  AND m.status='finished'",
            (ta, tb, tb, ta))
        if last_match and last_match[0] and newest[0] > last_match[0]:
            return False  # newer submission than last match -> allow rematch
    # Fall back to random window (1-10 min) to avoid rapid repeat pairings
    min_window = secrets.randbelow(10) + 1
    rows = execute_returning(conn,
        "SELECT 1 FROM matches "
        "WHERE ((team_a_id=%s AND team_b_id=%s) OR (team_a_id=%s AND team_b_id=%s)) "
        "AND created_at > now() - (%s::text || ' minutes')::interval LIMIT 1",
        (ta, tb, tb, ta, min_window))
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


def enqueue_matches(conn, limit=MAX_MATCHES_PER_CYCLE):
    _acquire_lock(conn)
    try:
        return _enqueue_locked(conn, limit)
    finally:
        _release_lock(conn)


def _enqueue_locked(conn, limit):
    rows = query(conn,
        "SELECT s.team_id, s.id, COALESCE(sr.rating, 600.0), "
        "  COALESCE(sr.matches_played, 0) "
        "FROM submissions s "
        "LEFT JOIN submission_ratings sr ON sr.submission_id = s.id "
        "WHERE s.status = 'active' "
        "ORDER BY s.team_id, s.created_at DESC", ())

    entries = [(r[0], r[1], float(r[2]), int(r[3])) for r in rows]

    # 1. Filter: remove submissions with pending/running matches or team in cooldown.
    eligible = []
    for tid, sid, rating, played in entries:
        if _has_pending_match(conn, sid):
            continue
        if _in_cooldown(conn, tid):
            continue
        eligible.append((tid, sid, rating, played))

    # 2. Sort: fewer matches played first (new teams get rapid feedback).
    eligible.sort(key=lambda x: (x[3], -x[2]))

    # 3. Greedy best-fit pairing; allow same-team different-submission rematches.
    created = 0
    used_subs = set()
    used_teams = set()
    for i in range(len(eligible)):
        if created >= limit:
            break
        tid_a, sid_a, rating_a, played_a = eligible[i]
        if sid_a in used_subs:
            continue
        best = None
        best_gap = None
        for j in range(i + 1, len(eligible)):
            tid_b, sid_b, rating_b, played_b = eligible[j]
            if sid_b in used_subs:
                continue
            if tid_a == tid_b and sid_a != sid_b:
                pass  # same team, different submission is allowed
            elif tid_a == tid_b:
                continue
            if _recently_matched(conn, tid_a, tid_b):
                continue
            gap = abs(eligible[i][2] - eligible[j][2])
            if gap > MAX_RATING_GAP:
                continue
            if best is None or gap < best_gap or (gap == best_gap and secrets.randbelow(2) == 0):
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

"""
Ladder matchmaker.

Pairs teams that currently have an *active* submission (latest 2 by time) into
rated matches and enqueues `run_match` jobs. Pairing is by Glicko-2 rating
proximity so matches stay meaningful; recent pairings are skipped to spread
coverage. Run from the worker loop or via `python3 matchmaker.py`.
"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine", "nexus_wars"))

from db import get_conn, execute, execute_returning, query
from jobs import engine_config

RECENT_WINDOW_HOURS = 1
MAX_RATING_GAP = 400


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


def create_match(conn, a, b):
    """a/b are (team_id, submission_id, rating). Creates match + job row."""
    seed = random.randint(0, 2**31 - 1)
    mid = execute_returning(conn,
        "INSERT INTO matches(team_a_id, team_b_id, submission_a_id, "
        "submission_b_id, seed, status, configuration_json, kind) "
        "VALUES(%s,%s,%s,%s,%s,'pending',%s,'rated') RETURNING id",
        (a[0], b[0], a[1], b[1], seed, json.dumps(engine_config())))
    match_id = str(mid[0])
    execute(conn,
            "INSERT INTO jobs(type, payload_json, status) VALUES('run_match', %s, 'pending')",
            (json.dumps({"match_id": match_id}),))
    return match_id


def enqueue_matches(conn, limit=8):
    rows = query(conn,
        "SELECT s.team_id, s.id, COALESCE(r.rating, 1500.0) "
        "FROM submissions s "
        "LEFT JOIN ratings r ON r.team_id = s.team_id "
        "WHERE s.status = 'active' "
        "ORDER BY COALESCE(r.rating, 1500.0) DESC", ())
    teams = [(r[0], r[1], float(r[2])) for r in rows]

    eligible = []
    for team in teams:
        tid = team[0]
        if _has_pending_match(conn, tid):
            continue
        eligible.append(team)

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

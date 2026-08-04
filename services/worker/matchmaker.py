import json
import os
import secrets
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine", "nexus_wars"))

from db import get_conn, execute, execute_returning, query
from jobs import engine_config

MATCHMAKER_LOCK = 87349201
RATING_GAP_SOFT_FACTOR = 0.20
RATING_GAP_HARD_FACTOR = 0.35
RECENCY_PENALTY_BASE = 20.0
LOAD_PENALTY_BASE = 4.0


def _acquire_lock(conn):
    """Acquire a session-level advisory lock so only one matchmaker runs."""
    execute(conn, "SELECT pg_advisory_lock(%s)", (MATCHMAKER_LOCK,))


def _release_lock(conn):
    execute(conn, "SELECT pg_advisory_unlock(%s)", (MATCHMAKER_LOCK,))


def _compute_dynamic_params(n_teams, rating_spread):
    """All matchmaking thresholds derived from live leaderboard state."""
    # Pair cooldown: 1.0 to 3.0 minutes to guarantee team variety and opponent rotation
    pair_cooldown = max(1.5, min(5.0, n_teams * 0.20))
    
    # Minimal agent cooldown: 3 seconds (0.05 min) so bots re-enter matching as soon as their match ends
    agent_cooldown = 0.05
    
    soft_gap = max(50.0, min(120.0, rating_spread * RATING_GAP_SOFT_FACTOR))
    hard_gap = max(100.0, min(200.0, rating_spread * RATING_GAP_HARD_FACTOR))
    
    per_team_hourly_cap = 999999  # Dynamic load balancing handled by load_penalty
    matches_per_cycle = max(4, n_teams)
    return pair_cooldown, agent_cooldown, soft_gap, hard_gap, per_team_hourly_cap, matches_per_cycle


def _get_pending_match_count(conn):
    """Backpressure check: count number of unassigned pending match jobs."""
    rows = execute_returning(conn,
        "SELECT COUNT(*) FROM jobs WHERE type='run_match' AND status='pending'", ())
    return int(rows[0]) if rows and rows[0] is not None else 0


def _recently_matched(conn, ta, tb, pair_cooldown_min=1.0):
    if ta == tb:
        rows = execute_returning(conn,
            "SELECT 1 FROM matches "
            "WHERE team_a_id=%s AND team_b_id=%s AND status='finished' "
            "AND finished_at > now() - interval '30 seconds' LIMIT 1",
            (ta, tb))
        return bool(rows)

    # Rematch window: if either team has a newer active submission than their
    # last match, allow rematch immediately.
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
            return False

    rows = execute_returning(conn,
        "SELECT 1 FROM matches "
        "WHERE ((team_a_id=%s AND team_b_id=%s) OR (team_a_id=%s AND team_b_id=%s)) "
        "AND status='finished' "
        "AND finished_at > now() - (%s * interval '1 minute') LIMIT 1",
        (ta, tb, tb, ta, float(pair_cooldown_min)))
    return bool(rows)


def _has_pending_match(conn, submission_id):
    rows = execute_returning(conn,
        "SELECT 1 FROM matches "
        "WHERE (submission_a_id=%s OR submission_b_id=%s) "
        "AND status IN ('pending', 'running') "
        "LIMIT 1",
        (submission_id, submission_id))
    return bool(rows)


def _in_cooldown(conn, submission_id, agent_cooldown_min=0.05):
    rows = execute_returning(conn,
        "SELECT 1 FROM matches "
        "WHERE (submission_a_id=%s OR submission_b_id=%s) "
        "AND status = 'finished' "
        "AND finished_at > now() - (%s * interval '1 minute') "
        "LIMIT 1",
        (submission_id, submission_id, float(agent_cooldown_min)))
    return bool(rows)


def _get_last_position(conn, ta, tb):
    """Determine who was Team A in their last match to swap home/away positions."""
    rows = execute_returning(conn,
        "SELECT team_a_id FROM matches "
        "WHERE ((team_a_id=%s AND team_b_id=%s) OR (team_a_id=%s AND team_b_id=%s)) "
        "AND status='finished' ORDER BY finished_at DESC LIMIT 1",
        (ta, tb, tb, ta))
    if rows and rows[0]:
        return str(rows[0])
    return None


def create_match(conn, a, b):
    """a/b are (team_id, submission_id). Rotates positions based on last match history."""
    last_a = _get_last_position(conn, a[0], b[0])
    if last_a == a[0]:
        # Swap positions to guarantee 50/50 home/away balance
        a, b = b, a

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
    """Clean up jobs and matches stuck in 'running' for > 5 minutes or 'pending' for > 15 minutes."""
    execute(conn,
        "UPDATE jobs SET status='failed', error='worker_timeout', finished_at=now() "
        "WHERE status='running' AND started_at < now() - interval '5 minutes'")
    execute(conn,
        "UPDATE matches SET status='errored', reason='worker_timeout', finished_at=now() "
        "WHERE status = 'running' AND created_at < now() - interval '10 minutes'")
    execute(conn,
        "UPDATE matches SET status='errored', reason='queue_timeout', finished_at=now() "
        "WHERE status = 'pending' AND created_at < now() - interval '15 minutes'")


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

    # Queue Backpressure Control: Check how many pending match jobs are in queue
    pending_queue_count = _get_pending_match_count(conn)
    max_allowed_pending = 50  # Higher cap prevents starvation when worker can't drain queue fast enough
    if pending_queue_count >= max_allowed_pending and limit_override is None:
        return 0

    rows = query(conn,
        "SELECT s.team_id, s.id, COALESCE(sr.rating, 600.0), "
        "  COALESCE(sr.matches_played, 0), COALESCE(sr.rd, 350.0) "
        "FROM submissions s "
        "LEFT JOIN submission_ratings sr ON sr.submission_id = s.id "
        "WHERE s.status = 'active' "
        "AND s.artifact_key IS NOT NULL AND s.artifact_key != '' "
        "ORDER BY s.created_at DESC", ())

    if not rows:
        return 0

    unique_teams = {r[0] for r in rows}
    n_teams = len(unique_teams)

    team_highest_active_rating = {}
    for r in rows:
        tid = r[0]
        rating = float(r[2])
        if tid not in team_highest_active_rating or rating > team_highest_active_rating[tid]:
            team_highest_active_rating[tid] = rating

    ratings = list(team_highest_active_rating.values())
    rating_spread = (max(ratings) - min(ratings)) if ratings else 0.0

    (pair_cooldown, agent_cooldown, soft_gap, hard_gap,
     per_team_hourly_cap, matches_per_cycle) = _compute_dynamic_params(n_teams, rating_spread)

    remaining_capacity = max_allowed_pending - pending_queue_count
    limit = limit_override if limit_override is not None else min(matches_per_cycle, remaining_capacity)
    if limit <= 0:
        return 0

    # Query hourly match counts per team
    recent_rows = query(conn,
        "SELECT tid, COUNT(*) FROM ("
        "  SELECT team_a_id AS tid FROM matches WHERE finished_at > now() - interval '60 minutes' AND status='finished'"
        "  UNION ALL "
        "  SELECT team_b_id AS tid FROM matches WHERE finished_at > now() - interval '60 minutes' AND status='finished'"
        ") t GROUP BY tid", ())
    team_hour_counts = {r[0]: int(r[1]) for r in recent_rows}
    avg_hour_matches = (sum(team_hour_counts.values()) / max(1, len(team_hour_counts))) if team_hour_counts else 0.0

    # Query last match time between pairs (in minutes ago) across all matches
    pair_rows = query(conn,
        "SELECT team_a_id, team_b_id, EXTRACT(EPOCH FROM (now() - MAX(created_at))) / 60.0 "
        "FROM matches GROUP BY team_a_id, team_b_id", ())
    pair_last_played = {}
    for r in pair_rows:
        ta, tb, mins = r[0], r[1], float(r[2]) if r[2] is not None else 999999.0
        pair_last_played[(ta, tb)] = min(pair_last_played.get((ta, tb), mins), mins)
        pair_last_played[(tb, ta)] = min(pair_last_played.get((tb, ta), mins), mins)

    # Query total match count between pairs to measure opponent diversity
    pair_counts_rows = query(conn,
        "SELECT team_a_id, team_b_id, COUNT(*) "
        "FROM matches WHERE status='finished' GROUP BY team_a_id, team_b_id", ())
    pair_match_counts = {}
    for r in pair_counts_rows:
        ta, tb, cnt = r[0], r[1], int(r[2])
        pair_match_counts[(ta, tb)] = pair_match_counts.get((ta, tb), 0) + cnt
        pair_match_counts[(tb, ta)] = pair_match_counts.get((tb, ta), 0) + cnt

    # Query last match time per team (in minutes ago)
    team_last_rows = query(conn,
        "SELECT tid, EXTRACT(EPOCH FROM (now() - MAX(finished_at))) / 60.0 "
        "FROM ("
        "  SELECT team_a_id AS tid, finished_at FROM matches WHERE status='finished'"
        "  UNION ALL "
        "  SELECT team_b_id AS tid, finished_at FROM matches WHERE status='finished'"
        ") t GROUP BY tid", ())
    team_last_match = {r[0]: float(r[1]) if r[1] is not None else 999999.0 for r in team_last_rows}

    # Batch query: which submissions are busy (pending/running) or in agent cooldown?
    # Single UNION replaces _has_pending_match + _in_cooldown per submission.
    busy_rows = query(conn,
        "SELECT DISTINCT submission_a_id AS sid FROM matches WHERE status IN ('pending','running') "
        "UNION "
        "SELECT DISTINCT submission_b_id FROM matches WHERE status IN ('pending','running') "
        "UNION "
        "SELECT DISTINCT submission_a_id FROM matches WHERE status='finished' "
        "    AND finished_at > now() - (%s * interval '1 minute') "
        "UNION "
        "SELECT DISTINCT submission_b_id FROM matches WHERE status='finished' "
        "    AND finished_at > now() - (%s * interval '1 minute')",
        (float(agent_cooldown), float(agent_cooldown)))
    busy_subs = {r[0] for r in busy_rows}

    # 1. Filter: remove submissions with pending/running matches or agent in cooldown.
    eligible = []
    for r in rows:
        tid, sid, actual_rating, played, rd = r[0], r[1], float(r[2]), int(r[3]), float(r[4])
        if sid in busy_subs:
            continue
        # Use submission-specific rating, not team's highest (fixes climb barrier)
        effective_rating = actual_rating
        eligible.append((tid, sid, effective_rating, played, rd))

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

                mins_ago = pair_last_played.get((tid_a, tid_b), 999999.0)
                if mins_ago < current_pair_cooldown:
                    continue

                h_count_a = team_hour_counts.get(tid_a, 0)
                h_count_b = team_hour_counts.get(tid_b, 0)
                mins_a = team_last_match.get(tid_a, 999999.0)
                mins_b = team_last_match.get(tid_b, 999999.0)

                is_starved_a = (h_count_a == 0) or (mins_a > 2.0)
                is_starved_b = (h_count_b == 0) or (mins_b > 2.0)
                is_uncal = (played_a == 0 or played_b == 0 or rd_a >= 300.0 or rd_b >= 300.0)

                gap = abs(rating_a - rating_b)

                # Hard ceiling: No match is EVER created across a >250 Elo gap (unless uncalibrated)
                if gap > 250.0 and not is_uncal:
                    continue

                # Dynamic Top-Tier Protection: Top teams (within 150 Elo of peak) only match within 220 Elo of peak
                top_r_a = max(team_highest_active_rating.get(tid_a, rating_a), rating_a)
                top_r_b = max(team_highest_active_rating.get(tid_b, rating_b), rating_b)
                max_ladder_rating = max(ratings) if ratings else 600.0
                top_tier_cutoff = max_ladder_rating - 150.0
                top_tier_min_allowed = max_ladder_rating - 220.0

                if max(top_r_a, top_r_b) >= top_tier_cutoff and min(top_r_a, top_r_b) < top_tier_min_allowed:
                    continue

                # Starved teams can bypass gap check, but only up to 1.2x hard_gap
                if gap > current_hard_gap and not (is_starved_a or is_starved_b or is_uncal):
                    continue
                if gap > current_hard_gap * 1.2 and not is_uncal:
                    continue

                # 1. Quadratic Elo Distance Penalty (30 Elo gap = 1.0, 100 Elo = 11.1, 200 Elo = 44.4)
                # If uncalibrated, remove the Elo penalty so they get priority matching and don't get starved by calibrated bots on the same team
                elo_penalty = 0.0 if is_uncal else (gap / 30.0) ** 2.0

                # 2. Smooth Recency Decay over 15-minute horizon (forces opponent rotation)
                mins_ago = pair_last_played.get((tid_a, tid_b), 999999.0)
                recency_penalty = 30.0 / (max(0.05, mins_ago) + 0.4)

                # 3. Opponent Diversity Penalty: strongly penalize repeated matchups
                times_played = pair_match_counts.get((tid_a, tid_b), 0)
                # Extra: if they played each other recently (last 30 min), add a steep cooldown
                mins_since_last = pair_last_played.get((tid_a, tid_b), 999999.0)
                recent_pair_penalty = max(0.0, (30.0 - mins_since_last) * 3.0) if mins_since_last < 30.0 else 0.0
                diversity_penalty = 35.0 * times_played + recent_pair_penalty

                # 4. Load Balancing & Info Gain
                overload = (max(0, h_count_a - avg_hour_matches) + max(0, h_count_b - avg_hour_matches))
                load_penalty = LOAD_PENALTY_BASE * overload
                info_gain_bonus = 0.5 * ((rd_a + rd_b) / 700.0)

                # 5. Capped Starvation Aging Boost
                starve_a = max(0.0, (mins_a - 1.5) / 0.5) if (h_count_a == 0 or mins_a > 1.5) else 0.0
                starve_b = max(0.0, (mins_b - 1.5) / 0.5) if (h_count_b == 0 or mins_b > 1.5) else 0.0
                starve_a = min(starve_a, 2.5)
                starve_b = min(starve_b, 2.5)
                starvation_boost = 2.0 * (starve_a + starve_b)

                cost = elo_penalty + recency_penalty + load_penalty + diversity_penalty - info_gain_bonus - starvation_boost
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

    # Pass 0: Guarantee matches for unrated/new players (matches_played==0 or rd>=300)
    # Sorts by highest RD (most uncertain) first for fastest convergence.
    uncal_sorted = sorted(
        [(eligible[i][4], i) for i in range(len(eligible))
         if eligible[i][3] == 0 or eligible[i][4] >= 300.0],
        reverse=True)
    for u in range(len(uncal_sorted)):
        if created >= limit:
            break
        _, idx_a = uncal_sorted[u]
        tid_a, sid_a, ra, _, _ = eligible[idx_a]
        if sid_a in used_subs or tid_a in used_teams:
            continue
        for v in range(u + 1, len(uncal_sorted)):
            _, idx_b = uncal_sorted[v]
            tid_b, sid_b, rb, _, _ = eligible[idx_b]
            if sid_b in used_subs or tid_b in used_teams or tid_b == tid_a:
                continue
            # Enforce top-tier protection and 250 Elo gap cap even for uncalibrated players
            top_r_a = max(team_highest_active_rating.get(tid_a, ra), ra)
            top_r_b = max(team_highest_active_rating.get(tid_b, rb), rb)
            max_ladder_rating = max(ratings) if ratings else 600.0
            if max(top_r_a, top_r_b) >= (max_ladder_rating - 150.0) and min(top_r_a, top_r_b) < (max_ladder_rating - 220.0):
                continue
            if abs(ra - rb) > 250.0:
                continue
            _pc = pair_last_played.get((tid_a, tid_b), 999999.0)
            if _pc < 0.5:
                continue
            create_match(conn, (tid_a, sid_a), (tid_b, sid_b))
            used_subs.update({sid_a, sid_b})
            used_teams.update({tid_a, tid_b})
            created += 1
            break

    # Pass 1: Standard matching with dynamic parameters
    find_and_create_pairs(hard_gap, pair_cooldown)

    # Pass 1b: Fallback relaxation if no matches were created
    if created == 0 and len(unique_teams) >= 2:
        find_and_create_pairs(hard_gap * 1.2, max(0.1, pair_cooldown * 0.15))

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
                _rm_mins = pair_last_played.get((tid_a, tid_b), 999999.0)
                if _rm_mins < pair_cooldown:
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

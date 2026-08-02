import os
import sys
import unittest.mock as mock

# Mock DB dependencies if running outside docker container without psycopg
if "psycopg" not in sys.modules:
    mock_db = mock.MagicMock()
    sys.modules["db"] = mock_db
    mock_jobs = mock.MagicMock()
    mock_jobs.engine_config = lambda: {}
    sys.modules["jobs"] = mock_jobs

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from matchmaker import _compute_dynamic_params, _get_pending_match_count, enqueue_matches


def test_dynamic_params_throughput():
    """Verify dynamic parameters support continuous high-throughput matchmaking with diversity."""
    for n_teams in [2, 5, 10, 20, 50]:
        pair_cd, agent_cd, soft_gap, hard_gap, per_team_cap, matches_per_cycle = _compute_dynamic_params(n_teams, 500.0)
        
        # Agent cooldown should be 0.05 min (3 seconds)
        assert agent_cd == 0.05, f"Agent cooldown should be 0.05: {agent_cd}"
        
        # Pair cooldown should be short (1.0 to 3.0 minutes) to guarantee opponent diversity
        assert pair_cd <= 3.0, f"Pair cooldown too high for n_teams={n_teams}: {pair_cd}"
        assert pair_cd >= 1.0
        
        # Hourly cap per team should be unlimited (999999)
        assert per_team_cap == 999999
        assert matches_per_cycle >= max(4, n_teams)


def test_backpressure_throttling():
    """Verify that enqueue_matches returns 0 if pending queue is full (>= 50 pending jobs)."""
    with mock.patch("matchmaker._acquire_lock"), \
         mock.patch("matchmaker._release_lock"), \
         mock.patch("matchmaker._reap_stuck_jobs"), \
         mock.patch("matchmaker._get_pending_match_count", return_value=51):
        
        mock_conn = mock.MagicMock()
        created = enqueue_matches(mock_conn)
        assert created == 0, f"Expected 0 matches enqueued under backpressure, got {created}"

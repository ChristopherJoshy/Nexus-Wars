-- Nexus Wars — migration 0005: matchmaking performance & correctness fixes

-- 1. Indexes for matches table
CREATE INDEX IF NOT EXISTS idx_matches_team_a ON matches(team_a_id);
CREATE INDEX IF NOT EXISTS idx_matches_team_b ON matches(team_b_id);
CREATE INDEX IF NOT EXISTS idx_matches_active ON matches(status, created_at) WHERE status IN ('pending', 'running');

-- 2. Backfill submission_ratings.matches_played from actual finished matches
UPDATE submission_ratings sr
SET matches_played = (
    SELECT COUNT(*)::int FROM matches m
    WHERE (m.submission_a_id = sr.submission_id OR m.submission_b_id = sr.submission_id)
    AND m.status = 'finished'
);

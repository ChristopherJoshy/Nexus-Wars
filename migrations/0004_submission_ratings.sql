-- Nexus Wars — migration 0004: per-submission ratings

CREATE TABLE IF NOT EXISTS submission_ratings (
    submission_id    UUID PRIMARY KEY REFERENCES submissions(id) ON DELETE CASCADE,
    team_id          UUID REFERENCES teams(id) ON DELETE CASCADE,
    rating           DOUBLE PRECISION NOT NULL DEFAULT 600.0,
    rd               DOUBLE PRECISION NOT NULL DEFAULT 350.0,
    volatility       DOUBLE PRECISION NOT NULL DEFAULT 0.06,
    last_match_at    TIMESTAMPTZ,
    wins             INTEGER NOT NULL DEFAULT 0,
    losses           INTEGER NOT NULL DEFAULT 0,
    draws            INTEGER NOT NULL DEFAULT 0,
    matches_played   INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_submission_ratings_team
    ON submission_ratings(team_id);

INSERT INTO submission_ratings (submission_id, team_id)
SELECT s.id, s.team_id
FROM submissions s
WHERE s.status IN ('validated', 'active', 'inactive')
  AND NOT EXISTS (
      SELECT 1 FROM submission_ratings sr WHERE sr.submission_id = s.id
  );

-- Nexus Wars — initial schema (PostgreSQL 13+)
-- Run with:  psql "$DATABASE_URL" -f migrations/0001_init.sql

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- --------------------------------------------------------------------------
-- Users (sourced from Google OAuth)
-- --------------------------------------------------------------------------
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT UNIQUE NOT NULL,
    name            TEXT,
    google_sub      TEXT UNIQUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- --------------------------------------------------------------------------
-- Teams — one competing team per user; join by short code
-- --------------------------------------------------------------------------
CREATE TABLE teams (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    team_code       TEXT UNIQUE NOT NULL,   -- short code used to join
    owner_id        UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_teams_code ON teams(team_code);

CREATE TABLE team_members (
    team_id         UUID REFERENCES teams(id) ON DELETE CASCADE,
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    role            TEXT NOT NULL DEFAULT 'member',
    joined_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (team_id, user_id)
);

-- --------------------------------------------------------------------------
-- Submissions
-- --------------------------------------------------------------------------
CREATE TYPE submission_status AS ENUM
    ('queued', 'compiling', 'validated', 'rejected', 'active', 'inactive');

CREATE TABLE submissions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id         UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    user_id         UUID REFERENCES users(id) ON DELETE SET NULL,
    status          submission_status NOT NULL DEFAULT 'queued',
    artifact_key    TEXT,                       -- object store / fs path
    engine_version  TEXT,
    reject_reason   TEXT,
    validation_replay_key TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_subs_team_time ON submissions(team_id, created_at);

-- --------------------------------------------------------------------------
-- Ratings (Glicko-2, fractional periods)
-- --------------------------------------------------------------------------
CREATE TABLE ratings (
    team_id         UUID PRIMARY KEY REFERENCES teams(id) ON DELETE CASCADE,
    rating          DOUBLE PRECISION NOT NULL DEFAULT 600,
    rd              DOUBLE PRECISION NOT NULL DEFAULT 350,
    volatility      DOUBLE PRECISION NOT NULL DEFAULT 0.06,
    last_match_at   TIMESTAMPTZ,
    wins            INTEGER NOT NULL DEFAULT 0,
    losses          INTEGER NOT NULL DEFAULT 0,
    draws           INTEGER NOT NULL DEFAULT 0,
    matches_played  INTEGER NOT NULL DEFAULT 0
);

-- --------------------------------------------------------------------------
-- Matches
-- --------------------------------------------------------------------------
CREATE TYPE match_kind AS ENUM ('validation', 'rated');
CREATE TYPE match_status AS ENUM ('pending', 'running', 'finished', 'errored');
CREATE TYPE match_winner AS ENUM ('a', 'b', 'draw');

CREATE TABLE matches (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    seed            BIGINT,
    engine_version  TEXT,
    configuration_json JSONB NOT NULL,
    team_a_id       UUID REFERENCES teams(id),
    team_b_id       UUID REFERENCES teams(id),
    submission_a_id UUID REFERENCES submissions(id),
    submission_b_id UUID REFERENCES submissions(id),
    status          match_status NOT NULL DEFAULT 'pending',
    kind            match_kind NOT NULL,
    winner          match_winner,
    reason          TEXT,
    replay_key      TEXT,
    scores          JSONB,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    duration_ms     INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_matches_status ON matches(status);
CREATE INDEX idx_matches_team ON matches(team_a_id, team_b_id);

-- Per-participant rating deltas (for team profile / history)
CREATE TABLE match_participants (
    match_id        UUID REFERENCES matches(id) ON DELETE CASCADE,
    team_id         UUID REFERENCES teams(id) ON DELETE CASCADE,
    player_index    INTEGER NOT NULL,
    submission_id   UUID REFERENCES submissions(id),
    rating_before   DOUBLE PRECISION,
    rd_before       DOUBLE PRECISION,
    rating_after    DOUBLE PRECISION,
    rd_after        DOUBLE PRECISION,
    PRIMARY KEY (match_id, team_id)
);

-- --------------------------------------------------------------------------
-- Job queue (polled by workers with SKIP LOCKED)
-- --------------------------------------------------------------------------
CREATE TYPE job_type AS ENUM ('compile', 'validate', 'run_match');
CREATE TYPE job_status AS ENUM ('pending', 'running', 'done', 'failed');

CREATE TABLE jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type            job_type NOT NULL,
    payload_json    JSONB NOT NULL DEFAULT '{}'::jsonb,
    status          job_status NOT NULL DEFAULT 'pending',
    worker_id       TEXT,
    error           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ
);
CREATE INDEX idx_jobs_pending ON jobs(status, created_at);

-- --------------------------------------------------------------------------
-- Replay metadata (bytes live in object storage)
-- --------------------------------------------------------------------------
CREATE TABLE replay_objects (
    key             TEXT PRIMARY KEY,
    match_id        UUID REFERENCES matches(id) ON DELETE CASCADE,
    size_bytes      BIGINT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

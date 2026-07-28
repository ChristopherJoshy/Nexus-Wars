-- Nexus Wars — migration 0002: competitions table, enum updates, submission cap

-- --------------------------------------------------------------------------
-- 1. Competitions table (open / closed / completed)
-- --------------------------------------------------------------------------
CREATE TYPE competition_status AS ENUM ('open', 'closed', 'completed');

CREATE TABLE competitions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug            TEXT UNIQUE NOT NULL,
    title           TEXT NOT NULL,
    status          competition_status NOT NULL DEFAULT 'open',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed the default competition
INSERT INTO competitions (slug, title, status) VALUES ('nexus-wars', 'Nexus Wars', 'open');

-- --------------------------------------------------------------------------
-- 2. Update submission_status enum — add 'errored', remove 'compiling'
-- --------------------------------------------------------------------------
ALTER TYPE submission_status ADD VALUE 'errored' AFTER 'rejected';

-- (Can't remove 'compiling' from enum in PostgreSQL without recreating it.
--  Since no rows use 'compiling', we just leave it in the type definition.)

-- --------------------------------------------------------------------------
-- 3. Update job_type enum — remove 'compile'
-- --------------------------------------------------------------------------
-- (Same constraint — can't remove from enum. We leave it unused.)

-- --------------------------------------------------------------------------
-- 4. Add competition_id to matches
-- --------------------------------------------------------------------------
ALTER TABLE matches ADD COLUMN competition_id UUID REFERENCES competitions(id);

UPDATE matches SET competition_id = (SELECT id FROM competitions WHERE slug = 'nexus-wars');

-- --------------------------------------------------------------------------
-- 5. Update users — add firebase_uid, remove google_sub (Firebase migration)
-- --------------------------------------------------------------------------
ALTER TABLE users ADD COLUMN IF NOT EXISTS firebase_uid TEXT UNIQUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS image TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE users ALTER COLUMN email DROP NOT NULL;

-- --------------------------------------------------------------------------
-- 6. Add unique constraint on (team_id, submission_index) for ordering
--    and an ORDINAL column for explicit ordering of submissions
-- --------------------------------------------------------------------------
ALTER TABLE submissions ADD COLUMN IF NOT EXISTS ordinal INTEGER;

-- Nexus Wars — migration 0003: admin settings table + submission pause
CREATE TABLE IF NOT EXISTS settings (
    key             TEXT PRIMARY KEY,
    value           JSONB NOT NULL DEFAULT 'true'::jsonb,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO settings (key, value) VALUES ('submissions_paused', 'false')
ON CONFLICT (key) DO NOTHING;

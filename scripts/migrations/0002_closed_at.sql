-- Migration 0002: explicit Close tracking
-- Adds closed_at column on {{TABLE}}.
-- Idempotent.

ALTER TABLE {{TABLE}} ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_{{TABLE}}_closed_at
    ON {{TABLE}}(closed_at) WHERE closed_at IS NOT NULL;

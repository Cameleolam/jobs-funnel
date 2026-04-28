-- Migration 0002: explicit Close tracking
-- Adds closed_at column on jobs.
-- Idempotent.

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_jobs_closed_at
    ON jobs(closed_at) WHERE closed_at IS NOT NULL;

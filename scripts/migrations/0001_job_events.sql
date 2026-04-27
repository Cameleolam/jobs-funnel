-- Migration 0001: job tracking timeline
-- Adds tracked_at column on jobs and a new job_events table.
-- Idempotent: safe to run multiple times.

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS tracked_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_jobs_tracked_at
    ON jobs(tracked_at) WHERE tracked_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS job_events (
    id           SERIAL PRIMARY KEY,
    job_id       INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    occurred_at  TIMESTAMPTZ NOT NULL,
    kind         TEXT NOT NULL CHECK (kind IN (
                     'application','contact','interview','task','decision','note'
                 )),
    label        TEXT NOT NULL,
    notes        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_job_events_job_id ON job_events(job_id);
CREATE INDEX IF NOT EXISTS idx_job_events_occurred_at ON job_events(occurred_at);

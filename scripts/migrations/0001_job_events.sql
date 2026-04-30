-- Migration 0001: job tracking timeline
-- Adds tracked_at column on {{TABLE}} and a new {{EVENTS_TABLE}} table.
-- Idempotent: safe to run multiple times.

ALTER TABLE {{TABLE}} ADD COLUMN IF NOT EXISTS tracked_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_{{TABLE}}_tracked_at
    ON {{TABLE}}(tracked_at) WHERE tracked_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS {{EVENTS_TABLE}} (
    id           SERIAL PRIMARY KEY,
    job_id       INTEGER NOT NULL REFERENCES {{TABLE}}(id) ON DELETE CASCADE,
    occurred_at  TIMESTAMPTZ NOT NULL,
    kind         TEXT NOT NULL CHECK (kind IN (
                     'application','contact','interview','task','decision','note'
                 )),
    label        TEXT NOT NULL,
    notes        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_{{EVENTS_TABLE}}_job_id ON {{EVENTS_TABLE}}(job_id);
CREATE INDEX IF NOT EXISTS idx_{{EVENTS_TABLE}}_occurred_at ON {{EVENTS_TABLE}}(occurred_at);

-- Migration 0001a: rename legacy job_events table to {{EVENTS_TABLE}} convention.
-- Background: 0001_job_events.sql originally created a literal `job_events` table.
-- The migration is now templated as `{{EVENTS_TABLE}}` so multiple profiles can
-- coexist (each profile's events table = `<TABLE>_events`). Existing DBs that
-- already have the literal `job_events` need a one-time rename.
--
-- Idempotent: only renames if the legacy table exists AND the templated one doesn't.

DO $$
BEGIN
    IF to_regclass('public.job_events') IS NOT NULL
       AND to_regclass('public.{{EVENTS_TABLE}}') IS NULL THEN
        EXECUTE 'ALTER TABLE job_events RENAME TO {{EVENTS_TABLE}}';
    END IF;
END $$;

-- Rename the legacy indexes if they're still on the old name pattern.
DO $$
BEGIN
    IF to_regclass('public.idx_job_events_job_id') IS NOT NULL
       AND to_regclass('public.idx_{{EVENTS_TABLE}}_job_id') IS NULL THEN
        EXECUTE 'ALTER INDEX idx_job_events_job_id RENAME TO idx_{{EVENTS_TABLE}}_job_id';
    END IF;
    IF to_regclass('public.idx_job_events_occurred_at') IS NOT NULL
       AND to_regclass('public.idx_{{EVENTS_TABLE}}_occurred_at') IS NULL THEN
        EXECUTE 'ALTER INDEX idx_job_events_occurred_at RENAME TO idx_{{EVENTS_TABLE}}_occurred_at';
    END IF;
END $$;

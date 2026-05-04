-- Migration 0004: pipeline_runs counters for embedding + dedup + scoring observability.
-- pipeline_runs is intentionally global (not per-profile), so {{TABLE}} is NOT used here.

ALTER TABLE pipeline_runs
    ADD COLUMN IF NOT EXISTS embed_count             INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS embed_failures          INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS embed_degraded          BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS dedup_vector_resolved   INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS dedup_claude_calls      INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS score_critique_count    INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS score_human_flagged     INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS score_uncalibrated      INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS score_rescored          INTEGER DEFAULT 0;

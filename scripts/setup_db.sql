-- Jobs Funnel - PostgreSQL Schema
-- Run via: python scripts/run_migration.py scripts/setup_db.sql
-- (Resolves {{TABLE}} / {{EVENTS_TABLE}} from JOBS_FUNNEL_TABLE.)
--
-- Or run with psql by pre-substituting placeholders manually:
--   sed 's/{{TABLE}}/jobs/g; s/{{EVENTS_TABLE}}/jobs_events/g' \
--     scripts/setup_db.sql | psql -U postgres

-- Create database (run this separately if needed):
-- CREATE DATABASE jobs_funnel;

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS {{TABLE}} (
    id              SERIAL PRIMARY KEY,
    url             TEXT NOT NULL UNIQUE,
    title           TEXT NOT NULL,
    company         TEXT NOT NULL DEFAULT '',
    location        TEXT NOT NULL DEFAULT '',
    description     TEXT NOT NULL DEFAULT '',
    description_quality TEXT DEFAULT 'unknown',  -- good/poor/empty/unknown
    source          TEXT NOT NULL,
    external_id     TEXT DEFAULT '',
    tags            JSONB DEFAULT '[]',
    remote          BOOLEAN DEFAULT FALSE,
    likely_english  BOOLEAN DEFAULT FALSE,
    staffing_agency BOOLEAN NOT NULL DEFAULT FALSE,
    geo_mismatch    BOOLEAN NOT NULL DEFAULT FALSE,
    salary_min      INTEGER,
    salary_max      INTEGER,
    salary_currency TEXT DEFAULT 'EUR',

    crawled_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    analyzed_at     TIMESTAMPTZ,

    status          TEXT NOT NULL DEFAULT 'pending',  -- pending/analyzed/error/dead
    error           TEXT,
    error_code      TEXT,                -- TIMEOUT/PARSE_FAIL/API_ERROR/EMPTY_DESCRIPTION/BATCH_PADDING/NO_RESULT

    fit_score       INTEGER,
    decision        TEXT,
    cv_variant      TEXT,
    hard_blockers   JSONB DEFAULT '[]',
    soft_gaps       JSONB DEFAULT '[]',
    strong_matches  JSONB DEFAULT '[]',
    reasoning       TEXT,
    priority_notes  TEXT,
    scoring_provider TEXT,
    scoring_model    TEXT,
    review_provider  TEXT,
    review_model     TEXT,
    base_fit_score   INTEGER,
    base_decision    TEXT,
    review_error     TEXT,
    needs_human_review BOOLEAN NOT NULL DEFAULT FALSE,
    explanation        TEXT,
    confidence         TEXT,
    critique_count     INTEGER NOT NULL DEFAULT 0,

    retry_count     INTEGER DEFAULT 0,
    sheet_synced    BOOLEAN DEFAULT FALSE,
    sheet_synced_at TIMESTAMPTZ,

    user_status     TEXT,             -- interested/applied/in_process/offer/rejected/dismissed/null
    applied_at      TIMESTAMPTZ,
    notes           TEXT,

    posted_at       TIMESTAMPTZ,      -- when the job was posted (from API)
    employment_type TEXT,              -- full-time/part-time/contract/freelance/minijob
    seniority_level TEXT,              -- junior/mid/senior/lead
    start_date      TEXT,              -- extracted start date (e.g. "sofort", "01.05.2026")

    possible_duplicate_of  INTEGER REFERENCES {{TABLE}}(id),
    duplicate_confirmed    BOOLEAN,           -- null=unreviewed, true=confirmed dup, false=not a dup
    embedding              vector(1024),
    embedding_calibration  vector(1024),
    embedded_at            TIMESTAMPTZ,
    embed_model            TEXT,
    embed_attempts         INTEGER NOT NULL DEFAULT 0,
    scored_uncalibrated    BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_{{TABLE}}_status ON {{TABLE}}(status);
CREATE INDEX IF NOT EXISTS idx_{{TABLE}}_sheet_synced ON {{TABLE}}(sheet_synced) WHERE sheet_synced = FALSE;
CREATE INDEX IF NOT EXISTS idx_{{TABLE}}_decision ON {{TABLE}}(decision);
CREATE INDEX IF NOT EXISTS idx_{{TABLE}}_error_code ON {{TABLE}}(error_code) WHERE error_code IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_{{TABLE}}_dead ON {{TABLE}}(status) WHERE status = 'dead';
CREATE INDEX IF NOT EXISTS idx_{{TABLE}}_needs_review
    ON {{TABLE}}(needs_human_review)
    WHERE needs_human_review = TRUE;
CREATE INDEX IF NOT EXISTS idx_{{TABLE}}_embedding
    ON {{TABLE}} USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
CREATE INDEX IF NOT EXISTS idx_{{TABLE}}_embedding_calibration
    ON {{TABLE}} USING hnsw (embedding_calibration vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
CREATE INDEX IF NOT EXISTS idx_{{TABLE}}_calibration_pool
    ON {{TABLE}} (user_status)
    WHERE embedding_calibration IS NOT NULL
      AND user_status IN ('interested','applied','in_process','offer','dismissed','rejected');
CREATE INDEX IF NOT EXISTS idx_{{TABLE}}_rescore
    ON {{TABLE}} (status)
    WHERE scored_uncalibrated = TRUE AND embedding_calibration IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_{{TABLE}}_embed_failed
    ON {{TABLE}} (id) WHERE error_code = 'EMBED_FAILED';

-- pipeline_runs and job_raw_data are global (not per-profile) — kept literal.
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id              SERIAL PRIMARY KEY,
    execution_id    TEXT,                              -- n8n $execution.id
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    trigger_type    TEXT NOT NULL DEFAULT 'manual',    -- manual/cron/webhook
    profile         TEXT NOT NULL DEFAULT '',
    jobs_crawled    INTEGER DEFAULT 0,
    jobs_inserted   INTEGER DEFAULT 0,
    jobs_analyzed   INTEGER DEFAULT 0,
    jobs_errored    INTEGER DEFAULT 0,
    embed_count     INTEGER DEFAULT 0,
    embed_failures  INTEGER DEFAULT 0,
    embed_degraded  BOOLEAN DEFAULT FALSE,
    dedup_vector_resolved INTEGER DEFAULT 0,
    dedup_claude_calls    INTEGER DEFAULT 0,
    score_critique_count INTEGER DEFAULT 0,
    score_human_flagged  INTEGER DEFAULT 0,
    score_uncalibrated   INTEGER DEFAULT 0,
    score_rescored       INTEGER DEFAULT 0,
    duration_ms     INTEGER,
    status          TEXT NOT NULL DEFAULT 'running',   -- running/success/partial/failed
    notes           TEXT
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_started_at ON pipeline_runs(started_at);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status ON pipeline_runs(status);

CREATE TABLE IF NOT EXISTS job_raw_data (
    id          SERIAL PRIMARY KEY,
    url         TEXT NOT NULL UNIQUE,
    raw_json    JSONB NOT NULL,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source      TEXT NOT NULL
);

-- ── Tracking timeline (added 2026-04) ────────────────────────────────
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

ALTER TABLE {{TABLE}} ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_{{TABLE}}_closed_at
    ON {{TABLE}}(closed_at) WHERE closed_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS {{TABLE}}_calibration_proposals (
    id                   BIGSERIAL PRIMARY KEY,
    status               TEXT NOT NULL DEFAULT 'proposed'
                         CHECK (status IN ('proposed', 'applied', 'rolled_back', 'rejected')),
    window_days          INTEGER NOT NULL DEFAULT 90,
    confidence           TEXT NOT NULL DEFAULT 'low',
    sample_counts        JSONB NOT NULL DEFAULT '{}'::jsonb,
    metrics              JSONB NOT NULL DEFAULT '{}'::jsonb,
    proposed_settings    JSONB NOT NULL,
    previous_settings    JSONB,
    rationale            JSONB NOT NULL DEFAULT '{}'::jsonb,
    error                TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    applied_at           TIMESTAMPTZ,
    rolled_back_at       TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS {{TABLE}}_calibration_settings (
    singleton              BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    active_proposal_id    BIGINT REFERENCES {{TABLE}}_calibration_proposals(id),
    review_low             INTEGER NOT NULL DEFAULT 4,
    review_high            INTEGER NOT NULL DEFAULT 6,
    calibration_k          INTEGER NOT NULL DEFAULT 3,
    calibration_k_batch    INTEGER NOT NULL DEFAULT 6,
    calibration_min_pool   INTEGER NOT NULL DEFAULT 3,
    weight_offer           DOUBLE PRECISION NOT NULL DEFAULT 1.5,
    weight_interview       DOUBLE PRECISION NOT NULL DEFAULT 1.4,
    weight_applied         DOUBLE PRECISION NOT NULL DEFAULT 1.2,
    weight_dismiss_note    DOUBLE PRECISION NOT NULL DEFAULT 1.2,
    weight_dismiss         DOUBLE PRECISION NOT NULL DEFAULT 0.8,
    weight_interested      DOUBLE PRECISION NOT NULL DEFAULT 0.7,
    source                 TEXT NOT NULL DEFAULT 'db',
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO {{TABLE}}_calibration_settings (singleton)
VALUES (TRUE)
ON CONFLICT (singleton) DO NOTHING;

CREATE INDEX IF NOT EXISTS idx_{{TABLE}}_calibration_proposals_created
    ON {{TABLE}}_calibration_proposals(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_{{TABLE}}_calibration_proposals_status
    ON {{TABLE}}_calibration_proposals(status);

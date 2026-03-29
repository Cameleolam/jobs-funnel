-- Jobs Funnel - PostgreSQL Schema
-- Run: psql -U postgres -f scripts/setup_db.sql

-- Create database (run this separately if needed):
-- CREATE DATABASE jobs_funnel;

-- Connect to jobs_funnel first, then run the rest:
-- \c jobs_funnel

CREATE TABLE IF NOT EXISTS jobs (
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

    retry_count     INTEGER DEFAULT 0,
    sheet_synced    BOOLEAN DEFAULT FALSE,
    sheet_synced_at TIMESTAMPTZ,

    user_status     TEXT,             -- applied/dismissed/null
    applied_at      TIMESTAMPTZ,
    notes           TEXT,

    posted_at       TIMESTAMPTZ,      -- when the job was posted (from API)
    employment_type TEXT,              -- full-time/part-time/contract/freelance/minijob
    seniority_level TEXT,              -- junior/mid/senior/lead
    start_date      TEXT               -- extracted start date (e.g. "sofort", "01.05.2026")
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_sheet_synced ON jobs(sheet_synced) WHERE sheet_synced = FALSE;
CREATE INDEX IF NOT EXISTS idx_jobs_decision ON jobs(decision);
CREATE INDEX IF NOT EXISTS idx_jobs_error_code ON jobs(error_code) WHERE error_code IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_jobs_dead ON jobs(status) WHERE status = 'dead';

CREATE TABLE IF NOT EXISTS job_raw_data (
    id          SERIAL PRIMARY KEY,
    url         TEXT NOT NULL UNIQUE,
    raw_json    JSONB NOT NULL,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source      TEXT NOT NULL
);

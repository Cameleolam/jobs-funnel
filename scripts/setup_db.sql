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

    status          TEXT NOT NULL DEFAULT 'pending',
    error           TEXT,

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
    notes           TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_sheet_synced ON jobs(sheet_synced) WHERE sheet_synced = FALSE;
CREATE INDEX IF NOT EXISTS idx_jobs_decision ON jobs(decision);

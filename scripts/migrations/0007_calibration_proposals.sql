-- Migration 0007: DB-backed calibration settings and proposal audit history.

CREATE TABLE IF NOT EXISTS {{TABLE}}_calibration_proposals (
    id                    BIGSERIAL PRIMARY KEY,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status                TEXT NOT NULL DEFAULT 'proposed'
                          CHECK (status IN ('proposed','applied','rolled_back','rejected')),
    window_days           INTEGER NOT NULL DEFAULT 90 CHECK (window_days > 0),
    min_review_decisions  INTEGER NOT NULL DEFAULT 30 CHECK (min_review_decisions > 0),
    min_outcomes          INTEGER NOT NULL DEFAULT 10 CHECK (min_outcomes > 0),
    confidence            TEXT NOT NULL DEFAULT 'low' CHECK (confidence IN ('low','medium','high')),
    sample_counts         JSONB NOT NULL DEFAULT '{}'::jsonb,
    metrics               JSONB NOT NULL DEFAULT '{}'::jsonb,
    proposed_settings     JSONB NOT NULL,
    previous_settings     JSONB,
    rationale             JSONB NOT NULL DEFAULT '{}'::jsonb,
    applied_at            TIMESTAMPTZ,
    rolled_back_at        TIMESTAMPTZ,
    error                 TEXT
);

CREATE TABLE IF NOT EXISTS {{TABLE}}_calibration_settings (
    singleton             BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    active_proposal_id    BIGINT REFERENCES {{TABLE}}_calibration_proposals(id),
    review_low            INTEGER NOT NULL DEFAULT 4 CHECK (review_low BETWEEN 0 AND 10),
    review_high           INTEGER NOT NULL DEFAULT 6 CHECK (review_high BETWEEN 0 AND 10),
    calibration_k         INTEGER NOT NULL DEFAULT 3 CHECK (calibration_k > 0),
    calibration_k_batch   INTEGER NOT NULL DEFAULT 6 CHECK (calibration_k_batch > 0),
    calibration_min_pool  INTEGER NOT NULL DEFAULT 3 CHECK (calibration_min_pool > 0),
    weight_offer          NUMERIC NOT NULL DEFAULT 1.5 CHECK (weight_offer > 0),
    weight_interview      NUMERIC NOT NULL DEFAULT 1.4 CHECK (weight_interview > 0),
    weight_applied        NUMERIC NOT NULL DEFAULT 1.2 CHECK (weight_applied > 0),
    weight_dismiss_note   NUMERIC NOT NULL DEFAULT 1.2 CHECK (weight_dismiss_note > 0),
    weight_dismiss        NUMERIC NOT NULL DEFAULT 0.8 CHECK (weight_dismiss > 0),
    weight_interested     NUMERIC NOT NULL DEFAULT 0.7 CHECK (weight_interested > 0),
    source                TEXT NOT NULL DEFAULT 'defaults',
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (review_low <= review_high)
);

CREATE INDEX IF NOT EXISTS idx_{{TABLE}}_calibration_proposals_created
    ON {{TABLE}}_calibration_proposals(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_{{TABLE}}_calibration_proposals_status
    ON {{TABLE}}_calibration_proposals(status);

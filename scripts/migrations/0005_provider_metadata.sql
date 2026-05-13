-- Migration 0005: Persist scoring/review provider metadata on profile jobs.

ALTER TABLE {{TABLE}}
    ADD COLUMN IF NOT EXISTS scoring_provider TEXT,
    ADD COLUMN IF NOT EXISTS scoring_model    TEXT,
    ADD COLUMN IF NOT EXISTS review_provider  TEXT,
    ADD COLUMN IF NOT EXISTS review_model     TEXT,
    ADD COLUMN IF NOT EXISTS base_fit_score   INTEGER,
    ADD COLUMN IF NOT EXISTS base_decision    TEXT,
    ADD COLUMN IF NOT EXISTS review_error     TEXT;

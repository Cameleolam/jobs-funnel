-- Migration 0006: Persist LangGraph human-review routing fields.

ALTER TABLE {{TABLE}}
    ADD COLUMN IF NOT EXISTS needs_human_review BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS explanation        TEXT,
    ADD COLUMN IF NOT EXISTS confidence         TEXT,
    ADD COLUMN IF NOT EXISTS critique_count     INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_{{TABLE}}_needs_review
    ON {{TABLE}}(needs_human_review)
    WHERE needs_human_review = TRUE;

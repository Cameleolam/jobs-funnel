from pathlib import Path


SQL = Path("scripts/setup_db.sql").read_text(encoding="utf-8")


def test_baseline_creates_profile_scoped_calibration_tables():
    assert "CREATE TABLE IF NOT EXISTS {{TABLE}}_calibration_proposals" in SQL
    assert "CREATE TABLE IF NOT EXISTS {{TABLE}}_calibration_settings" in SQL
    assert "active_proposal_id    BIGINT REFERENCES {{TABLE}}_calibration_proposals(id)" in SQL


def test_baseline_proposals_preserve_current_columns_and_constraints():
    assert "status                TEXT NOT NULL DEFAULT 'proposed'" in SQL
    assert "CHECK (status IN ('proposed','applied','rolled_back','rejected'))" in SQL
    assert "window_days           INTEGER NOT NULL DEFAULT 90 CHECK (window_days > 0)" in SQL
    assert "min_review_decisions  INTEGER NOT NULL DEFAULT 30 CHECK (min_review_decisions > 0)" in SQL
    assert "min_outcomes          INTEGER NOT NULL DEFAULT 10 CHECK (min_outcomes > 0)" in SQL
    assert "confidence            TEXT NOT NULL DEFAULT 'low' CHECK (confidence IN ('low','medium','high'))" in SQL


def test_baseline_settings_preserve_current_constraints_and_defaults():
    assert "review_low            INTEGER NOT NULL DEFAULT 4 CHECK (review_low BETWEEN 0 AND 10)" in SQL
    assert "review_high           INTEGER NOT NULL DEFAULT 6 CHECK (review_high BETWEEN 0 AND 10)" in SQL
    assert "calibration_k         INTEGER NOT NULL DEFAULT 3 CHECK (calibration_k > 0)" in SQL
    assert "calibration_k_batch   INTEGER NOT NULL DEFAULT 6 CHECK (calibration_k_batch > 0)" in SQL
    assert "calibration_min_pool  INTEGER NOT NULL DEFAULT 3 CHECK (calibration_min_pool > 0)" in SQL
    assert "source                TEXT NOT NULL DEFAULT 'defaults'" in SQL
    assert "CHECK (review_low <= review_high)" in SQL


def test_baseline_settings_preserve_numeric_weight_constraints():
    assert "weight_offer          NUMERIC NOT NULL DEFAULT 1.5 CHECK (weight_offer > 0)" in SQL
    assert "weight_interview      NUMERIC NOT NULL DEFAULT 1.4 CHECK (weight_interview > 0)" in SQL
    assert "weight_applied        NUMERIC NOT NULL DEFAULT 1.2 CHECK (weight_applied > 0)" in SQL
    assert "weight_dismiss_note   NUMERIC NOT NULL DEFAULT 1.2 CHECK (weight_dismiss_note > 0)" in SQL
    assert "weight_dismiss        NUMERIC NOT NULL DEFAULT 0.8 CHECK (weight_dismiss > 0)" in SQL
    assert "weight_interested     NUMERIC NOT NULL DEFAULT 0.7 CHECK (weight_interested > 0)" in SQL


def test_baseline_proposals_preserve_audit_and_rollback_columns():
    for column in (
        "created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()",
        "sample_counts         JSONB NOT NULL DEFAULT '{}'::jsonb",
        "metrics               JSONB NOT NULL DEFAULT '{}'::jsonb",
        "proposed_settings     JSONB NOT NULL",
        "previous_settings     JSONB",
        "rationale             JSONB NOT NULL DEFAULT '{}'::jsonb",
        "applied_at            TIMESTAMPTZ",
        "rolled_back_at        TIMESTAMPTZ",
        "error                 TEXT",
    ):
        assert column in SQL


def test_baseline_seeds_active_calibration_settings_row():
    assert "INSERT INTO {{TABLE}}_calibration_settings (singleton)" in SQL
    assert "ON CONFLICT (singleton) DO NOTHING" in SQL

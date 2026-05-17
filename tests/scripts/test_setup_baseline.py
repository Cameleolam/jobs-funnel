from pathlib import Path


SQL = Path("scripts/setup_db.sql").read_text(encoding="utf-8")


def test_setup_db_contains_pgvector_baseline():
    assert "CREATE EXTENSION IF NOT EXISTS vector" in SQL
    assert "embedding              vector(1024)" in SQL
    assert "embedding_calibration  vector(1024)" in SQL
    assert "USING hnsw (embedding vector_cosine_ops)" in SQL
    assert "USING hnsw (embedding_calibration vector_cosine_ops)" in SQL


def test_setup_db_contains_calibration_tables():
    assert "CREATE TABLE IF NOT EXISTS {{TABLE}}_calibration_proposals" in SQL
    assert "CREATE TABLE IF NOT EXISTS {{TABLE}}_calibration_settings" in SQL
    assert "min_review_decisions  INTEGER NOT NULL DEFAULT 30 CHECK (min_review_decisions > 0)" in SQL
    assert "min_outcomes          INTEGER NOT NULL DEFAULT 10 CHECK (min_outcomes > 0)" in SQL
    assert "confidence            TEXT NOT NULL DEFAULT 'low' CHECK (confidence IN ('low','medium','high'))" in SQL
    assert "CHECK (review_low <= review_high)" in SQL
    assert "source                TEXT NOT NULL DEFAULT 'defaults'" in SQL
    assert "INSERT INTO {{TABLE}}_calibration_settings (singleton)" in SQL


def test_setup_db_contains_provider_and_review_columns():
    assert "scoring_provider TEXT" in SQL
    assert "review_provider  TEXT" in SQL
    assert "needs_human_review BOOLEAN NOT NULL DEFAULT FALSE" in SQL


def test_setup_db_contains_existing_profile_table_upgrade_alters_before_indexes():
    alter_index = SQL.index("ALTER TABLE {{TABLE}}\n    ADD COLUMN IF NOT EXISTS embedding")
    first_dependent_index = SQL.index("CREATE INDEX IF NOT EXISTS idx_{{TABLE}}_needs_review")
    assert alter_index < first_dependent_index

    for column in [
        "ADD COLUMN IF NOT EXISTS embedding              vector(1024)",
        "ADD COLUMN IF NOT EXISTS embedding_calibration  vector(1024)",
        "ADD COLUMN IF NOT EXISTS embedded_at            TIMESTAMPTZ",
        "ADD COLUMN IF NOT EXISTS embed_model            TEXT",
        "ADD COLUMN IF NOT EXISTS embed_attempts         INTEGER NOT NULL DEFAULT 0",
        "ADD COLUMN IF NOT EXISTS scored_uncalibrated    BOOLEAN NOT NULL DEFAULT FALSE",
        "ADD COLUMN IF NOT EXISTS scoring_provider TEXT",
        "ADD COLUMN IF NOT EXISTS scoring_model    TEXT",
        "ADD COLUMN IF NOT EXISTS review_provider  TEXT",
        "ADD COLUMN IF NOT EXISTS review_model     TEXT",
        "ADD COLUMN IF NOT EXISTS base_fit_score   INTEGER",
        "ADD COLUMN IF NOT EXISTS base_decision    TEXT",
        "ADD COLUMN IF NOT EXISTS review_error     TEXT",
        "ADD COLUMN IF NOT EXISTS needs_human_review BOOLEAN NOT NULL DEFAULT FALSE",
        "ADD COLUMN IF NOT EXISTS explanation        TEXT",
        "ADD COLUMN IF NOT EXISTS confidence         TEXT",
        "ADD COLUMN IF NOT EXISTS critique_count     INTEGER NOT NULL DEFAULT 0",
    ]:
        assert column in SQL


def test_setup_db_contains_existing_pipeline_runs_upgrade_alters():
    assert "ALTER TABLE pipeline_runs" in SQL
    for column in [
        "ADD COLUMN IF NOT EXISTS embed_count             INTEGER DEFAULT 0",
        "ADD COLUMN IF NOT EXISTS embed_failures          INTEGER DEFAULT 0",
        "ADD COLUMN IF NOT EXISTS embed_degraded          BOOLEAN DEFAULT FALSE",
        "ADD COLUMN IF NOT EXISTS dedup_vector_resolved   INTEGER DEFAULT 0",
        "ADD COLUMN IF NOT EXISTS dedup_claude_calls      INTEGER DEFAULT 0",
        "ADD COLUMN IF NOT EXISTS score_critique_count    INTEGER DEFAULT 0",
        "ADD COLUMN IF NOT EXISTS score_human_flagged     INTEGER DEFAULT 0",
        "ADD COLUMN IF NOT EXISTS score_uncalibrated      INTEGER DEFAULT 0",
        "ADD COLUMN IF NOT EXISTS score_rescored          INTEGER DEFAULT 0",
    ]:
        assert column in SQL


def test_setup_db_renames_legacy_job_events_before_creating_scoped_events_table():
    rename_index = SQL.index("ALTER TABLE job_events RENAME TO {{EVENTS_TABLE}}")
    create_index = SQL.index("CREATE TABLE IF NOT EXISTS {{EVENTS_TABLE}}")
    assert rename_index < create_index
    assert "to_regclass('public.job_events')" in SQL
    assert "to_regclass('public.{{EVENTS_TABLE}}')" in SQL

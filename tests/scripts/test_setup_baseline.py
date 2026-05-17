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
    assert "INSERT INTO {{TABLE}}_calibration_settings (singleton)" in SQL


def test_setup_db_contains_provider_and_review_columns():
    assert "scoring_provider TEXT" in SQL
    assert "review_provider  TEXT" in SQL
    assert "needs_human_review BOOLEAN NOT NULL DEFAULT FALSE" in SQL

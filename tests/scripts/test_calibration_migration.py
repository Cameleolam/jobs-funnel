from pathlib import Path


SQL = Path("scripts/migrations/0007_calibration_proposals.sql").read_text(encoding="utf-8")


def test_migration_creates_profile_scoped_tables():
    assert "CREATE TABLE IF NOT EXISTS {{TABLE}}_calibration_settings" in SQL
    assert "CREATE TABLE IF NOT EXISTS {{TABLE}}_calibration_proposals" in SQL


def test_settings_table_has_active_settings_columns():
    for column in (
        "review_low",
        "review_high",
        "calibration_k",
        "calibration_k_batch",
        "calibration_min_pool",
        "weight_offer",
        "weight_interview",
        "weight_applied",
        "weight_dismiss_note",
        "weight_dismiss",
        "weight_interested",
        "active_proposal_id",
        "updated_at",
    ):
        assert column in SQL
    assert "review_low <= review_high" in SQL


def test_settings_table_seeds_singleton_row_idempotently():
    normalized_sql = " ".join(SQL.split())

    assert (
        "INSERT INTO {{TABLE}}_calibration_settings (singleton) "
        "VALUES (TRUE) ON CONFLICT (singleton) DO NOTHING;"
    ) in normalized_sql


def test_proposals_table_has_audit_and_rollback_columns():
    for column in (
        "status",
        "sample_counts",
        "metrics",
        "proposed_settings",
        "previous_settings",
        "rationale",
        "applied_at",
        "rolled_back_at",
    ):
        assert column in SQL
    assert "'proposed','applied','rolled_back','rejected'" in SQL.replace(" ", "")

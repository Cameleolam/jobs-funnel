from pathlib import Path


SQL = Path("scripts/setup_db.sql").read_text(encoding="utf-8")


def test_baseline_creates_profile_scoped_calibration_tables():
    assert "CREATE TABLE IF NOT EXISTS {{TABLE}}_calibration_proposals" in SQL
    assert "CREATE TABLE IF NOT EXISTS {{TABLE}}_calibration_settings" in SQL
    assert "active_proposal_id    BIGINT REFERENCES {{TABLE}}_calibration_proposals(id)" in SQL


def test_baseline_seeds_active_calibration_settings_row():
    assert "INSERT INTO {{TABLE}}_calibration_settings (singleton)" in SQL
    assert "ON CONFLICT (singleton) DO NOTHING" in SQL

from pathlib import Path


README = Path("README.md").read_text(encoding="utf-8")


def test_readme_does_not_reference_deleted_migration_files():
    assert "scripts/migrations/0001_job_events.sql" not in README
    assert "scripts/migrations/0007_calibration_proposals.sql" not in README
    assert "python scripts/run_migrations.py" in README

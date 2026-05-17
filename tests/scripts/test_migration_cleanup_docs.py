from pathlib import Path


README = Path("README.md").read_text(encoding="utf-8")
RUN_MIGRATION = Path("scripts/run_migration.py").read_text(encoding="utf-8")


def test_readme_does_not_reference_deleted_migration_files():
    deleted_migrations = [
        "scripts/migrations/0001_job_events.sql",
        "scripts/migrations/0001a_rename_legacy_events.sql",
        "scripts/migrations/0002_closed_at.sql",
        "scripts/migrations/0003_pgvector.sql",
        "scripts/migrations/0004_pipeline_metrics.sql",
        "scripts/migrations/0005_provider_metadata.sql",
        "scripts/migrations/0006_human_review.sql",
        "scripts/migrations/0007_calibration_proposals.sql",
    ]

    for migration in deleted_migrations:
        assert migration not in README
    assert "python scripts/run_migrations.py" in README


def test_run_migration_docs_point_to_batch_setup_runner():
    assert "scripts/migrations/0001_job_events.sql" not in RUN_MIGRATION
    assert "python scripts/run_migration.py <path_to_sql_file>" not in RUN_MIGRATION
    assert "python scripts/run_migrations.py" in RUN_MIGRATION
    assert "python scripts/run_migration.py --list" in RUN_MIGRATION

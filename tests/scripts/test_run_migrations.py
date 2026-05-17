from pathlib import Path
from unittest.mock import MagicMock

import scripts.run_migrations as rms


def test_sql_plan_runs_setup_db_before_migrations(tmp_path):
    setup = tmp_path / "setup_db.sql"
    setup.write_text("SELECT 'setup';", encoding="utf-8")
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0002_second.sql").write_text("SELECT 'second';", encoding="utf-8")
    (migrations / "0001_first.sql").write_text("SELECT 'first';", encoding="utf-8")

    paths = rms.sql_plan(setup_path=setup, migrations_dir=migrations)

    assert [p.name for p in paths] == [
        "setup_db.sql",
        "0001_first.sql",
        "0002_second.sql",
    ]


def test_sql_plan_allows_missing_migrations_dir(tmp_path):
    setup = tmp_path / "setup_db.sql"
    setup.write_text("SELECT 'setup';", encoding="utf-8")

    paths = rms.sql_plan(setup_path=setup, migrations_dir=tmp_path / "missing")

    assert [p.name for p in paths] == ["setup_db.sql"]


def test_apply_setup_runs_without_schema_migration_skip(monkeypatch, tmp_path):
    setup = tmp_path / "setup_db.sql"
    setup.write_text("SELECT '{{TABLE}}';", encoding="utf-8")
    cur = MagicMock()

    rms.apply_sql_file(cur, setup, "jobs_profile1", track=False)

    sql = cur.execute.call_args.args[0]
    assert "jobs_profile1" in sql
    assert "{{TABLE}}" not in sql


def test_apply_tracked_migration_skips_when_already_applied(monkeypatch, tmp_path):
    path = tmp_path / "0001_example.sql"
    path.write_text("SELECT 1;", encoding="utf-8")
    cur = MagicMock()
    monkeypatch.setattr(rms.run_migration, "already_applied", lambda cur, name, table: True)
    record = MagicMock()
    monkeypatch.setattr(rms.run_migration, "record_applied", record)

    result = rms.apply_sql_file(cur, path, "jobs_profile1", track=True)

    assert result == "skipped"
    assert cur.execute.call_count == 0
    record.assert_not_called()

from pathlib import Path
import subprocess
import sys
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


def test_default_plan_does_not_require_migrations_directory(tmp_path):
    setup = tmp_path / "setup_db.sql"
    setup.write_text("SELECT 1;", encoding="utf-8")
    missing = tmp_path / "migrations"

    paths = rms.sql_plan(setup_path=setup, migrations_dir=missing)

    assert [path.name for path in paths] == ["setup_db.sql"]


def test_apply_setup_runs_without_schema_migration_skip(monkeypatch, tmp_path):
    setup = tmp_path / "setup_db.sql"
    setup.write_text("SELECT '{{TABLE}}';", encoding="utf-8")
    cur = MagicMock()
    already_applied = MagicMock(side_effect=AssertionError("already_applied called"))
    monkeypatch.setattr(rms.run_migration, "already_applied", already_applied)

    rms.apply_sql_file(cur, setup, "jobs_profile1", track=False)

    sql = cur.execute.call_args.args[0]
    assert "jobs_profile1" in sql
    assert "{{TABLE}}" not in sql
    already_applied.assert_not_called()


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


def test_apply_tracked_migration_executes_and_records_when_pending(monkeypatch, tmp_path):
    path = tmp_path / "0001_example.sql"
    path.write_text("SELECT '{{TABLE}}';", encoding="utf-8")
    cur = MagicMock()
    monkeypatch.setattr(rms.run_migration, "already_applied", lambda cur, name, table: False)
    record = MagicMock()
    monkeypatch.setattr(rms.run_migration, "record_applied", record)

    result = rms.apply_sql_file(cur, path, "jobs_profile1", track=True)

    assert result == "applied"
    sql = cur.execute.call_args.args[0]
    assert "jobs_profile1" in sql
    record.assert_called_once_with(cur, "0001_example.sql", "jobs_profile1")


def test_run_validates_sql_files_before_connecting(monkeypatch, tmp_path):
    missing_setup = tmp_path / "missing_setup.sql"
    connect = MagicMock(side_effect=AssertionError("connect called"))
    monkeypatch.setattr(rms, "sql_plan", lambda: [missing_setup])
    monkeypatch.setattr(rms.run_migration, "connect", connect)

    try:
        rms.run()
    except FileNotFoundError as exc:
        assert exc.filename == str(missing_setup) or exc.args[0] == missing_setup
    else:
        raise AssertionError("FileNotFoundError not raised")
    connect.assert_not_called()


def test_run_sets_up_tracking_applies_setup_and_tracks_migrations(monkeypatch, tmp_path):
    setup = tmp_path / "setup_db.sql"
    setup.write_text("SELECT '{{TABLE}} setup';", encoding="utf-8")
    migration = tmp_path / "0001_example.sql"
    migration.write_text("SELECT '{{TABLE}} migration';", encoding="utf-8")
    cur = MagicMock()
    cursor_manager = MagicMock()
    cursor_manager.__enter__.return_value = cur
    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.cursor.return_value = cursor_manager
    ensure_tracking_table = MagicMock()
    already_applied = MagicMock(return_value=False)
    record_applied = MagicMock()

    monkeypatch.setattr(rms, "sql_plan", lambda: [setup, migration])
    monkeypatch.setenv("JOBS_FUNNEL_TABLE", "jobs_profile1")
    monkeypatch.setattr(rms.run_migration, "connect", lambda: conn)
    monkeypatch.setattr(rms.run_migration, "ensure_tracking_table", ensure_tracking_table)
    monkeypatch.setattr(rms.run_migration, "already_applied", already_applied)
    monkeypatch.setattr(rms.run_migration, "record_applied", record_applied)

    results = rms.run()

    assert results == [("setup_db.sql", "applied"), ("0001_example.sql", "applied")]
    ensure_tracking_table.assert_called_once_with(cur)
    already_applied.assert_called_once_with(cur, "0001_example.sql", "jobs_profile1")
    record_applied.assert_called_once_with(cur, "0001_example.sql", "jobs_profile1")
    assert cur.execute.call_args_list[0].args[0] == "SELECT 'jobs_profile1 setup';"
    assert cur.execute.call_args_list[1].args[0] == "SELECT 'jobs_profile1 migration';"
    conn.close.assert_called_once_with()


def test_main_prints_statuses(monkeypatch, capsys):
    monkeypatch.setattr(
        rms,
        "run",
        lambda: [("setup_db.sql", "applied"), ("0001_example.sql", "skipped")],
    )

    result = rms.main()

    captured = capsys.readouterr()
    assert result == 0
    assert "APPLIED setup_db.sql" in captured.out
    assert "SKIPPED 0001_example.sql" in captured.out
    assert captured.err == ""


def test_main_reports_failures(monkeypatch, capsys):
    monkeypatch.setattr(rms, "run", MagicMock(side_effect=RuntimeError("boom")))

    result = rms.main()

    captured = capsys.readouterr()
    assert result == 1
    assert captured.out == ""
    assert "Migration failed: boom" in captured.err


def test_direct_script_import_path_supports_scripts_package():
    result = subprocess.run(
        [sys.executable, "-c", "import run_migrations"],
        capture_output=True,
        text=True,
        check=False,
        cwd="scripts",
    )

    assert result.returncode == 0
    assert "No module named 'scripts'" not in result.stderr

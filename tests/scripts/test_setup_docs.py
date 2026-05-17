from pathlib import Path


ENV = Path(".env.template").read_text(encoding="utf-8")
README = Path("README.md").read_text(encoding="utf-8")
START = Path("start.bat").read_text(encoding="utf-8")


def test_env_template_defaults_to_codex_without_review_provider():
    assert "SCORING_PROVIDER=codex_gpt55_high" in ENV
    assert "SCORING_REVIEW_PROVIDER=" in ENV.splitlines()
    assert "SCORING_CLAUDE_CMD=claude" in ENV


def test_readme_uses_apply_all_migration_command():
    assert "python scripts/run_migrations.py" in README
    assert "python scripts/run_migration.py scripts/migrations/0007_calibration_proposals.sql" not in README
    assert "psql -h localhost -U postgres -d jobs_funnel -f scripts/setup_db.sql" not in README


def test_readme_documents_optional_claude_configuration():
    assert "`SCORING_CLAUDE_CMD` | `claude`" in README
    assert "Claude calls hanging when configured" in README


def test_readme_documents_workflow_reimport_rule():
    assert "workflow_template.json" in README
    assert "scripts/n8n/*.js" in README
    assert "profiles/<profile>/search.json" in README
    assert "Python script, UI, README, and migration changes do not require n8n workflow reimport." in README


def test_readme_points_to_doctor_troubleshooting_command():
    assert "python scripts/doctor.py" in README


def test_start_bat_points_to_doctor_and_ui():
    assert "python scripts\\doctor.py" in START or "python scripts/doctor.py" in START
    assert "http://localhost:8080" in START
    assert "Docker startup failed." in START
    assert "Doctor checks failed." in START
    assert START.count("exit /b %ERRORLEVEL%") >= 2
    assert "docker compose up -d" in START
    assert "npx dotenv -e .env -- n8n start" in START
    assert START.index("python scripts\\doctor.py") < START.index("npx dotenv -e .env -- n8n start")

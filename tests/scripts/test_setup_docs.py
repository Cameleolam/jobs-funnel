from pathlib import Path


ENV = Path(".env.template").read_text(encoding="utf-8")
README = Path("README.md").read_text(encoding="utf-8")
START = Path("start.bat").read_text(encoding="utf-8")
PROFILES_README = Path("profiles/README.md").read_text(encoding="utf-8")
SETUP_PROFILE = Path("scripts/setup_profile.py").read_text(encoding="utf-8")


def test_env_template_defaults_to_codex_without_review_provider():
    assert "SCORING_PROVIDER=codex_gpt55_high" in ENV
    assert "SCORING_REVIEW_PROVIDER=" in ENV.splitlines()
    assert "SCORING_CLAUDE_CMD=claude" in ENV


def test_readme_uses_apply_all_migration_command():
    assert "python scripts/run_migrations.py" in README
    assert "python scripts/run_migration.py scripts/migrations/0007_calibration_proposals.sql" not in README
    assert "psql -h localhost -U postgres -d jobs_funnel -f scripts/setup_db.sql" not in README
    assert "Jobs per filter batch" in README
    assert "Jobs per Claude filter batch" not in README


def test_readme_config_model_is_not_primary_scoring_config():
    assert "Claude model for scoring and dedup" not in README
    assert "Scoring is selected through environment variables, not `config.json`." in README
    assert "legacy" in README.lower()
    assert "SCORING_*" in README


def test_readme_manual_n8n_start_uses_dotenv():
    assert "npx dotenv -e .env -- n8n start" in README
    assert "```bash\nn8n start\n```" not in README


def test_profile_setup_docs_use_migration_runner():
    assert "python scripts/run_migrations.py" in PROFILES_README
    assert "JOBS_FUNNEL_TABLE" in PROFILES_README
    assert ".env" in PROFILES_README
    assert "setup_db.sql" not in PROFILES_README
    assert "setup_db.sql" not in SETUP_PROFILE
    assert "psql -U postgres -d jobs_funnel -f scripts/setup_db.sql" not in SETUP_PROFILE
    assert "python scripts/run_migrations.py" in SETUP_PROFILE


def test_readme_selects_profile_before_running_migrations():
    profile_index = README.index("python scripts/setup_profile.py myprofile")
    migration_index = README.index("python scripts/run_migrations.py")

    assert profile_index < migration_index


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
    docker_command = "docker compose up -d"
    doctor_command = "python scripts\\doctor.py --prestart"
    ui_command = "python -m uvicorn ui.server:app --port 8080 --reload"
    ui_url = "http://localhost:8080"
    n8n_command = "npx dotenv -e .env -- n8n start"

    assert doctor_command in START or "python scripts/doctor.py --prestart" in START
    assert ui_url in START
    assert "Docker startup failed." in START
    assert "Doctor checks failed." in START
    assert START.count("exit /b %ERRORLEVEL%") >= 2
    assert docker_command in START
    assert ui_command in START
    assert n8n_command in START

    docker_index = START.index(docker_command)
    doctor_index = START.index(doctor_command)
    ui_command_index = START.index(ui_command)
    ui_url_index = START.index(ui_url)
    n8n_index = START.index(n8n_command)

    assert docker_index < doctor_index
    assert doctor_index < ui_command_index
    assert doctor_index < ui_url_index
    assert ui_command_index < n8n_index
    assert ui_url_index < n8n_index

    docker_failure_block = START[docker_index:doctor_index]
    doctor_failure_block = START[doctor_index:ui_command_index]
    assert "Docker startup failed." in docker_failure_block
    assert "exit /b %ERRORLEVEL%" in docker_failure_block
    assert "Doctor checks failed." in doctor_failure_block
    assert "exit /b %ERRORLEVEL%" in doctor_failure_block

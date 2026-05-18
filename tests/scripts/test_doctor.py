from unittest.mock import MagicMock

import scripts.doctor as doctor


DOCTOR_ENV_VARS = [
    "JOBS_FUNNEL_PROJECT_DIR",
    "JOBS_FUNNEL_PROFILE",
    "JOBS_FUNNEL_TABLE",
    "JOBS_FUNNEL_N8N_BASE",
    "OLLAMA_URL",
    "EMBEDDING_MODEL",
    "SCORING_PROVIDER",
    "SCORING_REVIEW_PROVIDER",
    "SCORING_CODEX_CMD",
    "SCORING_CLAUDE_CMD",
]


def clear_doctor_env(monkeypatch):
    for name in DOCTOR_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_check_result_lines_include_next_action():
    check = doctor.CheckResult(
        name="n8n",
        status="fail",
        message="n8n is not reachable at http://localhost:5678",
        action="Start n8n with: n8n start",
    )

    assert check.lines() == [
        "FAIL n8n - n8n is not reachable at http://localhost:5678",
        "     Start n8n with: n8n start",
    ]


def test_exit_code_is_zero_when_no_failures():
    checks = [
        doctor.CheckResult("postgres", "ok", "Postgres reachable"),
        doctor.CheckResult("workflow", "warn", "workflow.json may need import"),
    ]

    assert doctor.exit_code(checks) == 0


def test_exit_code_is_nonzero_when_required_check_fails():
    checks = [doctor.CheckResult("postgres", "fail", "Postgres unavailable")]

    assert doctor.exit_code(checks) == 1


def test_check_command_available_reports_missing(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)

    result = doctor.check_command_available("codex", required=True)

    assert result.status == "fail"
    assert "codex was not found on PATH" in result.message
    assert result.action == "Install codex or update PATH."


def test_check_required_env_values_reports_blank_values(monkeypatch):
    clear_doctor_env(monkeypatch)
    monkeypatch.setenv("JOBS_FUNNEL_PROFILE", "profile1")
    monkeypatch.setenv("JOBS_FUNNEL_TABLE", "jobs")

    result = doctor.check_required_env_values()

    assert result.status == "fail"
    assert "JOBS_FUNNEL_PROJECT_DIR" in result.message
    assert "Fill JOBS_FUNNEL_PROJECT_DIR" in result.action


def test_check_required_env_values_passes_when_required_values_exist(monkeypatch, tmp_path):
    clear_doctor_env(monkeypatch)
    monkeypatch.setenv("JOBS_FUNNEL_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("JOBS_FUNNEL_PROFILE", "profile1")
    monkeypatch.setenv("JOBS_FUNNEL_TABLE", "jobs_profile1")

    result = doctor.check_required_env_values()

    assert result.status == "ok"


def test_check_profile_files_reports_missing_profile_inputs(monkeypatch, tmp_path):
    clear_doctor_env(monkeypatch)
    monkeypatch.setenv("JOBS_FUNNEL_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("JOBS_FUNNEL_PROFILE", "profile1")

    result = doctor.check_profile_files()

    assert result.status == "fail"
    assert "required profile files are missing" in result.message
    assert "profile1" in result.action


def test_check_profile_files_passes_when_profile_inputs_exist(monkeypatch, tmp_path):
    clear_doctor_env(monkeypatch)
    profile_dir = tmp_path / "profiles" / "profile1"
    profile_dir.mkdir(parents=True)
    (profile_dir / "search.json").write_text("{}", encoding="utf-8")
    (profile_dir / "filter_prompt.md").write_text("score jobs", encoding="utf-8")
    monkeypatch.setenv("JOBS_FUNNEL_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("JOBS_FUNNEL_PROFILE", "profile1")

    result = doctor.check_profile_files()

    assert result.status == "ok"
    assert result.message == "profile files exist for profile1"


def test_check_url_uses_get_and_reports_ok(monkeypatch):
    response = MagicMock(status_code=200)
    get = MagicMock(return_value=response)
    monkeypatch.setattr(doctor.httpx, "get", get)

    result = doctor.check_url("n8n", "http://localhost:5678")

    get.assert_called_once_with("http://localhost:5678", timeout=2.0)
    assert result.status == "ok"
    assert result.message == "n8n reachable at http://localhost:5678"


def test_check_url_reports_http_error_as_fail(monkeypatch):
    def raise_error(url, timeout):
        raise doctor.httpx.HTTPError("connection failed")

    monkeypatch.setattr(doctor.httpx, "get", raise_error)

    result = doctor.check_url("n8n", "http://localhost:5678")

    assert result.status == "fail"
    assert result.message == "n8n is not reachable at http://localhost:5678"
    assert result.action == "Start n8n and retry."


def test_check_url_reports_server_error_as_fail(monkeypatch):
    response = MagicMock(status_code=503)
    monkeypatch.setattr(doctor.httpx, "get", lambda url, timeout: response)

    result = doctor.check_url("n8n", "http://localhost:5678")

    assert result.status == "fail"
    assert result.message == "n8n returned HTTP 503"
    assert result.action == "Open http://localhost:5678 and inspect logs."


def test_collect_checks_default_provider_uses_codex_command_env(monkeypatch):
    commands = []
    urls = []
    clear_doctor_env(monkeypatch)
    monkeypatch.setattr(doctor, "load_dotenv", lambda path: None)
    monkeypatch.setattr(doctor, "check_env_file", lambda: doctor.CheckResult(".env", "ok", ".env exists"))
    monkeypatch.setattr(
        doctor,
        "check_workflow_file",
        lambda: doctor.CheckResult("workflow", "ok", "workflow.json exists"),
    )
    monkeypatch.setenv("JOBS_FUNNEL_N8N_BASE", "http://n8n.local:5678")
    monkeypatch.setenv("OLLAMA_URL", "http://ollama.local:11434/")
    monkeypatch.setenv("SCORING_CODEX_CMD", "codex-local")
    monkeypatch.setenv("SCORING_CLAUDE_CMD", "claude-local")

    def record_command(command, *, required):
        commands.append((command, required))
        return doctor.CheckResult(command, "ok", f"{command} is available")

    def record_url(name, url):
        urls.append((name, url))
        return doctor.CheckResult(name, "ok", f"{name} reachable at {url}")

    monkeypatch.setattr(doctor, "check_command_available", record_command)
    monkeypatch.setattr(doctor, "check_url", record_url)

    doctor.collect_checks()

    assert ("codex-local", True) in commands
    assert ("npx", True) in commands
    assert ("dotenv", True) in commands
    assert ("claude-local", True) not in commands
    assert urls == [("n8n", "http://n8n.local:5678")]


def test_collect_checks_prestart_skips_n8n_reachability(monkeypatch):
    commands = []
    urls = []
    clear_doctor_env(monkeypatch)
    monkeypatch.setattr(doctor, "load_dotenv", lambda path: None)
    monkeypatch.setattr(doctor, "check_env_file", lambda: doctor.CheckResult(".env", "ok", ".env exists"))
    monkeypatch.setattr(
        doctor,
        "check_workflow_file",
        lambda: doctor.CheckResult("workflow", "ok", "workflow.json exists"),
    )
    def record_command(command, *, required):
        commands.append((command, required))
        return doctor.CheckResult(command, "ok", f"{command} is available")

    monkeypatch.setattr(doctor, "check_command_available", record_command)
    monkeypatch.setenv("JOBS_FUNNEL_N8N_BASE", "http://n8n.local:5678")
    monkeypatch.setenv("OLLAMA_URL", "http://ollama.local:11434/")
    monkeypatch.setenv("SCORING_CODEX_CMD", "codex-local")

    def record_url(name, url):
        urls.append((name, url))
        return doctor.CheckResult(name, "ok", f"{name} reachable at {url}")

    monkeypatch.setattr(doctor, "check_url", record_url)

    doctor.collect_checks(prestart=True)

    assert ("npx", True) in commands
    assert ("dotenv", True) in commands
    assert ("n8n", "http://n8n.local:5678") not in urls


def test_main_prestart_flag_uses_prestart_checks(monkeypatch):
    calls = []
    monkeypatch.setattr(
        doctor,
        "collect_checks",
        lambda *, prestart=False: calls.append(prestart) or [doctor.CheckResult("ok", "ok", "ok")],
    )

    result = doctor.main(["--prestart"])

    assert result == 0
    assert calls == [True]


def test_collect_checks_claude_provider_uses_claude_command_env(monkeypatch):
    commands = []
    clear_doctor_env(monkeypatch)
    monkeypatch.setattr(doctor, "load_dotenv", lambda path: None)
    monkeypatch.setattr(doctor, "check_env_file", lambda: doctor.CheckResult(".env", "ok", ".env exists"))
    monkeypatch.setattr(
        doctor,
        "check_workflow_file",
        lambda: doctor.CheckResult("workflow", "ok", "workflow.json exists"),
    )
    monkeypatch.setenv("JOBS_FUNNEL_N8N_BASE", "http://n8n.local:5678")
    monkeypatch.setenv("OLLAMA_URL", "http://ollama.local:11434/")
    monkeypatch.setenv("SCORING_PROVIDER", "claude_sonnet")
    monkeypatch.setenv("SCORING_REVIEW_PROVIDER", "")
    monkeypatch.setenv("SCORING_CODEX_CMD", "codex-local")
    monkeypatch.setenv("SCORING_CLAUDE_CMD", "claude-local")
    monkeypatch.setattr(doctor, "check_url", lambda name, url: doctor.CheckResult(name, "ok", "reachable"))

    def record_command(command, *, required):
        commands.append((command, required))
        return doctor.CheckResult(command, "ok", f"{command} is available")

    monkeypatch.setattr(doctor, "check_command_available", record_command)

    doctor.collect_checks()

    assert ("codex-local", False) in commands
    assert ("claude-local", True) in commands


def test_collect_checks_embedding_model_adds_ollama_url_check(monkeypatch):
    urls = []
    clear_doctor_env(monkeypatch)
    monkeypatch.setattr(doctor, "load_dotenv", lambda path: None)
    monkeypatch.setattr(doctor, "check_env_file", lambda: doctor.CheckResult(".env", "ok", ".env exists"))
    monkeypatch.setattr(
        doctor,
        "check_workflow_file",
        lambda: doctor.CheckResult("workflow", "ok", "workflow.json exists"),
    )
    monkeypatch.setattr(
        doctor,
        "check_command_available",
        lambda command, *, required: doctor.CheckResult(command, "ok", f"{command} is available"),
    )
    monkeypatch.setenv("JOBS_FUNNEL_N8N_BASE", "http://n8n.local:5678")
    monkeypatch.setenv("EMBEDDING_MODEL", "nomic-embed-text")
    monkeypatch.setenv("OLLAMA_URL", "http://ollama.local:11434/")
    monkeypatch.setenv("SCORING_PROVIDER", "codex_gpt55_high")
    monkeypatch.setenv("SCORING_REVIEW_PROVIDER", "")
    monkeypatch.setenv("SCORING_CODEX_CMD", "codex-local")
    monkeypatch.setenv("SCORING_CLAUDE_CMD", "claude-local")

    def record_url(name, url):
        urls.append((name, url))
        return doctor.CheckResult(name, "ok", f"{name} reachable at {url}")

    monkeypatch.setattr(doctor, "check_url", record_url)

    doctor.collect_checks()

    assert ("n8n", "http://n8n.local:5678") in urls
    assert ("ollama", "http://ollama.local:11434") in urls

from unittest.mock import MagicMock

import scripts.doctor as doctor


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


def test_check_url_uses_get_and_reports_ok(monkeypatch):
    response = MagicMock(status_code=200)
    monkeypatch.setattr(doctor.httpx, "get", lambda url, timeout: response)

    result = doctor.check_url("n8n", "http://localhost:5678")

    assert result.status == "ok"
    assert result.message == "n8n reachable at http://localhost:5678"

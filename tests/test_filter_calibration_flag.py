import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.llm.types import ProviderError, ProviderTimeout


FIXTURES = Path(__file__).resolve().parent / "fixtures"
FILTER_PROMPT = FIXTURES / "filter_prompt.md"


def _argv_for_payload(payload):
    raw = json.dumps(payload).encode("utf-8")
    encoded = base64.b64encode(raw).decode("ascii")
    return ["filter.py", "--base64", encoded]


def _assert_parse_update_fallback(item, error_code):
    assert item["fit_score"] == 0
    assert item["decision"] == "SKIP"
    assert isinstance(item["hard_blockers"], list)
    assert item["error_code"] == error_code


def _load_filter(monkeypatch):
    monkeypatch.setenv("JOBS_FUNNEL_PROFILE", "test")
    import importlib
    import scripts.filter as fil

    importlib.reload(fil)
    monkeypatch.setattr(fil, "PROMPT_FILE", FILTER_PROMPT)
    return fil


def test_filter_uses_scoring_provider_env(monkeypatch, capsys):
    monkeypatch.setenv("SCORING_PROVIDER", "codex_gpt55_high")
    fil = _load_filter(monkeypatch)

    job = {"title": "T", "description": "D"}
    monkeypatch.setattr(sys, "argv", _argv_for_payload(job))
    expected = {
        "fit_score": 7,
        "decision": "PASS",
        "cv_variant": "software",
        "scoring_provider": "codex_gpt55_high",
    }
    calls = []

    def fake_score_input(*, parsed_input, system_prompt, config, root):
        calls.append(
            {
                "parsed_input": parsed_input,
                "system_prompt": system_prompt,
                "config": config,
                "root": root,
                "provider_env": os.environ["SCORING_PROVIDER"],
            }
        )
        return expected

    monkeypatch.setattr(fil, "score_input", fake_score_input)

    fil.main()

    assert calls == [
        {
            "parsed_input": job,
            "system_prompt": FILTER_PROMPT.read_text(encoding="utf-8"),
            "config": fil.CONFIG,
            "root": fil.PIPELINE_DIR,
            "provider_env": "codex_gpt55_high",
        }
    ]
    assert json.loads(capsys.readouterr().out) == expected


def test_filter_prints_array_output_from_score_input(monkeypatch, capsys):
    fil = _load_filter(monkeypatch)

    batch = [{"title": "A"}, {"title": "B"}]
    expected = [{"fit_score": 1}, {"fit_score": 9}]
    monkeypatch.setattr(sys, "argv", _argv_for_payload(batch))
    monkeypatch.setattr(fil, "score_input", lambda **kwargs: expected)

    fil.main()

    assert json.loads(capsys.readouterr().out) == expected


def test_filter_timeout_on_batch_returns_parse_update_compatible_fallbacks(monkeypatch, capsys):
    fil = _load_filter(monkeypatch)

    batch = [{"title": "A"}, {"title": "B"}]
    monkeypatch.setattr(sys, "argv", _argv_for_payload(batch))

    def raise_error(**kwargs):
        raise ProviderTimeout("codex_gpt55_high", "timed out", stderr="slow", stdout="partial")

    monkeypatch.setattr(fil, "score_input", raise_error)

    with pytest.raises(SystemExit) as raised:
        fil.main()

    assert raised.value.code == 1
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list)
    assert len(payload) == 2
    for item in payload:
        _assert_parse_update_fallback(item, "TIMEOUT")
        assert any("timed out" in blocker for blocker in item["hard_blockers"])
        assert item["reasoning"] == "codex_gpt55_high timed out after 300 seconds"


def test_filter_provider_error_on_batch_returns_api_error_fallbacks(monkeypatch, capsys):
    fil = _load_filter(monkeypatch)

    batch = [{"title": "A"}, {"title": "B"}]
    monkeypatch.setattr(sys, "argv", _argv_for_payload(batch))

    def raise_error(**kwargs):
        raise ProviderError("claude_sonnet", "scoring provider failed", stderr="e" * 600, stdout="o" * 600)

    monkeypatch.setattr(fil, "score_input", raise_error)

    with pytest.raises(SystemExit) as raised:
        fil.main()

    assert raised.value.code == 1
    payload = json.loads(capsys.readouterr().out)
    assert len(payload) == 2
    for item in payload:
        _assert_parse_update_fallback(item, "API_ERROR")
        assert any("Filter error" in blocker for blocker in item["hard_blockers"])
        assert item["reasoning"] == "scoring provider failed"
        assert item["stderr"] == "e" * 500
        assert item["stdout"] == "o" * 500


def test_filter_invalid_json_returns_parse_fail_fallback_without_traceback(monkeypatch, capsys):
    fil = _load_filter(monkeypatch)

    monkeypatch.setattr(sys, "argv", ["filter.py", "--base64", base64.b64encode(b"{not json").decode("ascii")])

    with pytest.raises(SystemExit) as raised:
        fil.main()

    captured = capsys.readouterr()
    assert raised.value.code == 1
    payload = json.loads(captured.out)
    _assert_parse_update_fallback(payload, "PARSE_FAIL")
    assert "Parse error" in payload["hard_blockers"][0]
    assert "Parse error" in payload["reasoning"]
    assert "Traceback" not in captured.err


def test_filter_invalid_base64_returns_api_error_fallback_without_traceback(monkeypatch, capsys):
    fil = _load_filter(monkeypatch)

    monkeypatch.setattr(sys, "argv", ["filter.py", "--base64", "not valid base64!"])

    with pytest.raises(SystemExit) as raised:
        fil.main()

    captured = capsys.readouterr()
    assert raised.value.code == 1
    payload = json.loads(captured.out)
    _assert_parse_update_fallback(payload, "API_ERROR")
    assert "Filter error" in payload["hard_blockers"][0]
    assert "Traceback" not in captured.err


def test_filter_base64_file_reads_base64_from_file_path(monkeypatch, capsys, tmp_path):
    fil = _load_filter(monkeypatch)

    job = {"title": "From File"}
    b64_path = tmp_path / "payload.b64"
    b64_path.write_text(base64.b64encode(json.dumps(job).encode("utf-8")).decode("ascii"), encoding="utf-8")
    calls = []
    monkeypatch.setattr(sys, "argv", ["filter.py", "--base64-file", str(b64_path)])
    monkeypatch.setattr(
        fil,
        "score_input",
        lambda **kwargs: calls.append(kwargs["parsed_input"]) or {"fit_score": 9, "decision": "PASS"},
    )

    fil.main()

    assert calls == [job]
    assert json.loads(capsys.readouterr().out)["fit_score"] == 9


def test_filter_stdin_input_calls_score_input(monkeypatch, capsys):
    fil = _load_filter(monkeypatch)

    job = {"title": "From Stdin"}
    calls = []
    monkeypatch.setattr(sys, "argv", ["filter.py"])
    monkeypatch.setattr(sys, "stdin", type("FakeStdin", (), {"read": lambda self: json.dumps(job)})())
    monkeypatch.setattr(
        fil,
        "score_input",
        lambda **kwargs: calls.append(kwargs["parsed_input"]) or {"fit_score": 5, "decision": "MAYBE"},
    )

    fil.main()

    assert calls == [job]
    assert json.loads(capsys.readouterr().out)["decision"] == "MAYBE"


def test_filter_file_path_input_calls_score_input(monkeypatch, capsys, tmp_path):
    fil = _load_filter(monkeypatch)

    job = {"title": "From Json File"}
    input_path = tmp_path / "job.json"
    input_path.write_text(json.dumps(job), encoding="utf-8")
    calls = []
    monkeypatch.setattr(sys, "argv", ["filter.py", str(input_path)])
    monkeypatch.setattr(
        fil,
        "score_input",
        lambda **kwargs: calls.append(kwargs["parsed_input"]) or {"fit_score": 6, "decision": "PASS"},
    )

    fil.main()

    assert calls == [job]
    assert json.loads(capsys.readouterr().out)["decision"] == "PASS"


def test_filter_script_direct_invocation_keeps_package_import_working():
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["JOBS_FUNNEL_PROFILE"] = "profile1"

    result = subprocess.run(
        [sys.executable, str(repo / "scripts" / "filter.py")],
        input="",
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )

    assert result.returncode == 1
    assert "No input provided on stdin" in result.stdout
    assert "ModuleNotFoundError" not in result.stderr

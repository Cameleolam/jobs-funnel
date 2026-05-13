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


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (
            ProviderTimeout("codex_gpt55_high", "timed out", stderr="slow", stdout="partial"),
            {
                "error": "codex_gpt55_high timed out after 300 seconds",
                "error_code": "TIMEOUT",
            },
        ),
        (
            ProviderError("claude_sonnet", "provider failed", stderr="e" * 600, stdout="o" * 600),
            {
                "error": "provider failed",
                "error_code": "API_ERROR",
                "stderr": "e" * 500,
                "stdout": "o" * 500,
            },
        ),
    ],
)
def test_filter_translates_provider_errors(monkeypatch, capsys, exc, expected):
    fil = _load_filter(monkeypatch)

    monkeypatch.setattr(sys, "argv", _argv_for_payload({"title": "T"}))

    def raise_error(**kwargs):
        raise exc

    monkeypatch.setattr(fil, "score_input", raise_error)

    with pytest.raises(SystemExit) as raised:
        fil.main()

    assert raised.value.code == 1
    assert json.loads(capsys.readouterr().out) == expected


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

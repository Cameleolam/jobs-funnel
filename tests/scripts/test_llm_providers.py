import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.llm.providers import (
    ClaudeCliProvider,
    CodexCliProvider,
    OllamaProvider,
    provider_from_key,
    review_band,
)
from scripts.llm import ScoringProvider
from scripts.llm.types import ProviderError, ProviderRequest, ProviderTimeout


def _completed(stdout='{"result":"[]"}', stderr="", returncode=0):
    result = MagicMock()
    result.stdout = stdout
    result.stderr = stderr
    result.returncode = returncode
    return result


def test_claude_provider_uses_claude_p_without_anthropic_api(monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["input"] = kwargs["input"]
        return _completed(stdout=json.dumps({"result": "[{\"fit_score\": 8}]"}))

    monkeypatch.setattr(subprocess, "run", fake_run)
    provider = ClaudeCliProvider(provider_key="claude_sonnet", model="claude-sonnet-4-6")

    response = provider.generate(ProviderRequest("SYSTEM", "USER", cwd=Path("D:/repo")))

    assert seen["cmd"] == [
        "claude",
        "-p",
        "--model",
        "claude-sonnet-4-6",
        "--output-format",
        "json",
        "--append-system-prompt",
        "SYSTEM",
        "--max-turns",
        "3",
        "--tools",
        "",
    ]
    assert seen["input"] == "USER"
    assert response.text == "[{\"fit_score\": 8}]"


def test_codex_provider_uses_read_only_exec_and_embeds_system_prompt(monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["input"] = kwargs["input"]
        return _completed(stdout='[{"fit_score": 7}]')

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("shutil.which", lambda command: None)
    provider = CodexCliProvider(
        provider_key="codex_gpt55_high",
        model="gpt-5.5",
        reasoning_effort="high",
        command="codex",
    )

    response = provider.generate(ProviderRequest("SYSTEM", "USER", cwd=Path("D:/repo")))

    assert seen["cmd"] == [
        "codex",
        "exec",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "-m",
        "gpt-5.5",
        "-c",
        'model_reasoning_effort="high"',
        "-s",
        "read-only",
        "--cd",
        "D:\\repo",
        "-",
    ]
    assert "Do not browse, read files, or use tools." in seen["input"]
    assert "<SCORING_SYSTEM_PROMPT>\nSYSTEM\n</SCORING_SYSTEM_PROMPT>" in seen["input"]
    assert "<USER_TASK>\nUSER\n</USER_TASK>" in seen["input"]
    assert response.text == '[{"fit_score": 7}]'


def test_codex_provider_wraps_cmd_files_on_windows(monkeypatch):
    monkeypatch.setattr("os.name", "nt")
    provider = CodexCliProvider(
        provider_key="codex_gpt55_high",
        model="gpt-5.5",
        reasoning_effort="high",
        command=r"D:\tools\npm-global\codex.cmd",
    )

    assert provider._command_prefix() == ["cmd.exe", "/c", r"D:\tools\npm-global\codex.cmd"]


def test_codex_provider_wraps_bat_files_on_windows(monkeypatch):
    monkeypatch.setattr("os.name", "nt")
    provider = CodexCliProvider(
        provider_key="codex_gpt55_high",
        model="gpt-5.5",
        reasoning_effort="high",
        command=r"D:\tools\codex.bat",
    )

    assert provider._command_prefix() == ["cmd.exe", "/c", r"D:\tools\codex.bat"]


def test_codex_provider_wraps_bare_command_resolved_to_cmd_on_windows(monkeypatch):
    monkeypatch.setattr("os.name", "nt")
    monkeypatch.setattr("shutil.which", lambda command: r"D:\tools\npm-global\codex.cmd")
    provider = CodexCliProvider(
        provider_key="codex_gpt55_high",
        model="gpt-5.5",
        reasoning_effort="high",
        command="codex",
    )

    assert provider._command_prefix() == ["cmd.exe", "/c", r"D:\tools\npm-global\codex.cmd"]


def test_provider_timeout_maps_to_provider_timeout(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=300)

    monkeypatch.setattr(subprocess, "run", fake_run)
    provider = ClaudeCliProvider(provider_key="claude_sonnet", model="claude-sonnet-4-6")

    with pytest.raises(ProviderTimeout) as exc:
        provider.generate(ProviderRequest("SYSTEM", "USER"))

    assert exc.value.error_code == "TIMEOUT"


def test_claude_launch_failure_maps_to_provider_error(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise FileNotFoundError("claude not found")

    monkeypatch.setattr(subprocess, "run", fake_run)
    provider = ClaudeCliProvider(provider_key="claude_sonnet", model="claude-sonnet-4-6")

    with pytest.raises(ProviderError) as exc:
        provider.generate(ProviderRequest("SYSTEM", "USER"))

    assert exc.value.provider_key == "claude_sonnet"
    assert "Failed to launch claude_sonnet" in str(exc.value)


def test_codex_launch_failure_maps_to_provider_error(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise PermissionError("access denied")

    monkeypatch.setattr(subprocess, "run", fake_run)
    provider = CodexCliProvider(
        provider_key="codex_gpt55_high",
        model="gpt-5.5",
        reasoning_effort="high",
        command="codex",
    )

    with pytest.raises(ProviderError) as exc:
        provider.generate(ProviderRequest("SYSTEM", "USER"))

    assert exc.value.provider_key == "codex_gpt55_high"
    assert "Failed to launch codex_gpt55_high" in str(exc.value)


def test_ollama_provider_posts_generate_json(monkeypatch):
    seen = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"response": "[{\"fit_score\": 5}]"}

    def fake_post(url, json, timeout):
        seen["url"] = url
        seen["json"] = json
        seen["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("httpx.post", fake_post)
    provider = OllamaProvider(
        provider_key="ollama_local",
        model="llama3.1:8b",
        url="http://localhost:11434",
    )

    response = provider.generate(ProviderRequest("SYSTEM", "USER", timeout_seconds=42))

    assert seen["url"] == "http://localhost:11434/api/generate"
    assert seen["json"]["model"] == "llama3.1:8b"
    assert seen["json"]["system"] == "SYSTEM"
    assert seen["json"]["prompt"] == "USER"
    assert seen["json"]["stream"] is False
    assert seen["json"]["format"] == "json"
    assert seen["timeout"] == 42
    assert response.text == "[{\"fit_score\": 5}]"


def test_ollama_invalid_json_maps_to_provider_error(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            raise ValueError("invalid json")

    monkeypatch.setattr("httpx.post", lambda url, json, timeout: FakeResponse())
    provider = OllamaProvider(
        provider_key="ollama_local",
        model="llama3.1:8b",
        url="http://localhost:11434",
    )

    with pytest.raises(ProviderError) as exc:
        provider.generate(ProviderRequest("SYSTEM", "USER"))

    assert exc.value.provider_key == "ollama_local"
    assert "Invalid Ollama JSON response" in str(exc.value)


def test_provider_from_key_defaults_and_env(monkeypatch):
    monkeypatch.delenv("SCORING_CLAUDE_MODEL", raising=False)
    monkeypatch.delenv("SCORING_CODEX_MODEL", raising=False)
    monkeypatch.setenv("SCORING_CODEX_CMD", r"D:\tools\npm-global\codex.cmd")

    claude = provider_from_key("claude_sonnet", {"model": "claude-sonnet-4-6"})
    codex = provider_from_key("codex_gpt55_high", {"model": "ignored"})

    assert claude.model == "claude-sonnet-4-6"
    assert codex.model == "gpt-5.5"
    assert codex.reasoning_effort == "high"
    assert codex.command == r"D:\tools\npm-global\codex.cmd"


def test_provider_from_key_env_overrides_claude_sonnet_model(monkeypatch):
    monkeypatch.setenv("SCORING_CLAUDE_MODEL", "claude-env-model")

    claude = provider_from_key("claude_sonnet", {"model": "config-model"})

    assert claude.model == "claude-env-model"


def test_scoring_provider_is_exported_from_package():
    assert ScoringProvider.__name__ == "ScoringProvider"


def test_review_band_defaults_to_four_through_six(monkeypatch):
    monkeypatch.delenv("SCORING_REVIEW_LOW", raising=False)
    monkeypatch.delenv("SCORING_REVIEW_HIGH", raising=False)

    assert review_band() == (4, 6)

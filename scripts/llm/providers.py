from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Protocol

import httpx

from scripts.llm.parsing import extract_result_text
from scripts.llm.types import ProviderError, ProviderRequest, ProviderResponse, ProviderTimeout


class ScoringProvider(Protocol):
    provider_key: str
    model: str

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        ...


def _elapsed_seconds(started: float) -> float:
    return round(time.monotonic() - started, 3)


def _cwd_text(cwd: Path | None) -> str:
    return str(cwd or Path.cwd())


def _provider_timeout(provider_key: str, exc: subprocess.TimeoutExpired) -> ProviderTimeout:
    return ProviderTimeout(
        provider_key=provider_key,
        message=f"{provider_key} timed out after {exc.timeout} seconds",
        stderr=(exc.stderr or "") if isinstance(exc.stderr, str) else "",
        stdout=(exc.stdout or "") if isinstance(exc.stdout, str) else "",
    )


def _provider_launch_error(provider_key: str, command: list[str], exc: OSError) -> ProviderError:
    return ProviderError(
        provider_key=provider_key,
        message=f"Failed to launch {provider_key} command {command[0]!r}: {exc}",
    )


class ClaudeCliProvider:
    def __init__(self, provider_key: str, model: str, command: str = "claude"):
        self.provider_key = provider_key
        self.model = model
        self.command = command

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        cmd = [
            self.command,
            "-p",
            "--model",
            self.model,
            "--output-format",
            "json",
            "--append-system-prompt",
            request.system_prompt,
            "--max-turns",
            "3",
            "--tools",
            "",
        ]
        started = time.monotonic()
        try:
            result = subprocess.run(
                cmd,
                input=request.user_prompt,
                capture_output=True,
                text=True,
                timeout=request.timeout_seconds,
                encoding="utf-8",
                errors="replace",
                cwd=request.cwd,
            )
        except subprocess.TimeoutExpired as exc:
            raise _provider_timeout(self.provider_key, exc) from exc
        except OSError as exc:
            raise _provider_launch_error(self.provider_key, cmd, exc) from exc

        if result.returncode != 0:
            raise ProviderError(
                self.provider_key,
                f"{self.provider_key} exited with code {result.returncode}",
                stderr=result.stderr,
                stdout=result.stdout,
            )

        return ProviderResponse(
            provider_key=self.provider_key,
            model=self.model,
            text=extract_result_text(result.stdout),
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
            elapsed_seconds=_elapsed_seconds(started),
        )


class CodexCliProvider:
    def __init__(
        self,
        provider_key: str,
        model: str,
        reasoning_effort: str,
        command: str = "codex",
    ):
        self.provider_key = provider_key
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.command = command

    def _command_prefix(self) -> list[str]:
        if os.name == "nt":
            resolved = shutil.which(self.command) or self.command
            suffix = Path(resolved).suffix.lower()
            if suffix in {".cmd", ".bat"}:
                return ["cmd.exe", "/c", resolved]
        return [self.command]

    def _stdin_prompt(self, request: ProviderRequest) -> str:
        return "\n".join(
            [
                "You are a deterministic job scoring subprocess.",
                "Do not browse, read files, or use tools.",
                "Return only the requested JSON.",
                "",
                "<SCORING_SYSTEM_PROMPT>",
                request.system_prompt,
                "</SCORING_SYSTEM_PROMPT>",
                "",
                "<USER_TASK>",
                request.user_prompt,
                "</USER_TASK>",
            ]
        )

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        cmd = [
            *self._command_prefix(),
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "-m",
            self.model,
            "-c",
            f'model_reasoning_effort="{self.reasoning_effort}"',
            "-s",
            "read-only",
            "--cd",
            _cwd_text(request.cwd),
            "-",
        ]
        started = time.monotonic()
        try:
            result = subprocess.run(
                cmd,
                input=self._stdin_prompt(request),
                capture_output=True,
                text=True,
                timeout=request.timeout_seconds,
                encoding="utf-8",
                errors="replace",
                cwd=request.cwd,
            )
        except subprocess.TimeoutExpired as exc:
            raise _provider_timeout(self.provider_key, exc) from exc
        except OSError as exc:
            raise _provider_launch_error(self.provider_key, cmd, exc) from exc

        if result.returncode != 0:
            raise ProviderError(
                self.provider_key,
                f"{self.provider_key} exited with code {result.returncode}",
                stderr=result.stderr,
                stdout=result.stdout,
            )

        return ProviderResponse(
            provider_key=self.provider_key,
            model=self.model,
            text=extract_result_text(result.stdout),
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
            elapsed_seconds=_elapsed_seconds(started),
        )


class OllamaProvider:
    def __init__(self, provider_key: str, model: str, url: str):
        self.provider_key = provider_key
        self.model = model
        self.url = url.rstrip("/")

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        started = time.monotonic()
        try:
            response = httpx.post(
                f"{self.url}/api/generate",
                json={
                    "model": self.model,
                    "system": request.system_prompt,
                    "prompt": request.user_prompt,
                    "stream": False,
                    "format": "json",
                },
                timeout=request.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(self.provider_key, str(exc)) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(self.provider_key, str(exc)) from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderError(self.provider_key, f"Invalid Ollama JSON response: {exc}") from exc
        text = body.get("response", "")
        if not isinstance(text, str):
            raise ProviderError(self.provider_key, "Ollama response field was not text")

        return ProviderResponse(
            provider_key=self.provider_key,
            model=self.model,
            text=text,
            stdout=text,
            stderr="",
            returncode=0,
            elapsed_seconds=_elapsed_seconds(started),
        )


def review_band() -> tuple[int, int]:
    return (
        int(os.getenv("SCORING_REVIEW_LOW", "4")),
        int(os.getenv("SCORING_REVIEW_HIGH", "6")),
    )


def provider_from_key(key: str, config: dict) -> ScoringProvider:
    if key == "claude_sonnet":
        return ClaudeCliProvider(
            provider_key=key,
            model=os.getenv("SCORING_CLAUDE_MODEL") or config.get("model", "claude-sonnet-4-6"),
            command=os.getenv("SCORING_CLAUDE_CMD", "claude"),
        )
    if key == "claude_haiku":
        return ClaudeCliProvider(
            provider_key=key,
            model=os.getenv("SCORING_HAIKU_MODEL", "haiku"),
            command=os.getenv("SCORING_CLAUDE_CMD", "claude"),
        )
    if key == "codex_gpt55_high":
        return CodexCliProvider(
            provider_key=key,
            model=os.getenv("SCORING_CODEX_MODEL", "gpt-5.5"),
            reasoning_effort="high",
            command=os.getenv("SCORING_CODEX_CMD", "codex"),
        )
    if key == "codex_gpt55_xhigh":
        return CodexCliProvider(
            provider_key=key,
            model=os.getenv("SCORING_CODEX_MODEL", "gpt-5.5"),
            reasoning_effort="xhigh",
            command=os.getenv("SCORING_CODEX_CMD", "codex"),
        )
    if key == "ollama_local":
        model = os.getenv("SCORING_OLLAMA_MODEL", "")
        if not model:
            raise ProviderError(key, "SCORING_OLLAMA_MODEL is required for ollama_local")
        return OllamaProvider(
            provider_key=key,
            model=model,
            url=os.getenv("SCORING_OLLAMA_URL", "http://localhost:11434"),
        )
    raise ProviderError(key, f"Unknown scoring provider: {key}")

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProviderRequest:
    system_prompt: str
    user_prompt: str
    timeout_seconds: int = 300
    cwd: Path | None = None


@dataclass(frozen=True)
class ProviderResponse:
    provider_key: str
    model: str
    text: str
    stdout: str
    stderr: str
    returncode: int
    elapsed_seconds: float


class ProviderError(Exception):
    error_code = "API_ERROR"

    def __init__(self, provider_key: str, message: str, stderr: str = "", stdout: str = ""):
        super().__init__(message)
        self.provider_key = provider_key
        self.stderr = stderr
        self.stdout = stdout


class ProviderTimeout(ProviderError):
    error_code = "TIMEOUT"

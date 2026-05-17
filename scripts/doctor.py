"""Human-readable local setup and health checker."""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx
from dotenv import load_dotenv


Status = Literal["ok", "warn", "fail"]
PROJECT_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: Status
    message: str
    action: str = ""

    def lines(self) -> list[str]:
        head = f"{self.status.upper():4} {self.name} - {self.message}"
        if not self.action:
            return [head]
        return [head, f"     {self.action}"]


def check_command_available(command: str, *, required: bool) -> CheckResult:
    if shutil.which(command):
        return CheckResult(command, "ok", f"{command} is available")
    status: Status = "fail" if required else "warn"
    return CheckResult(
        command,
        status,
        f"{command} was not found on PATH",
        f"Install {command} or update PATH.",
    )


def check_url(name: str, url: str) -> CheckResult:
    try:
        response = httpx.get(url, timeout=2.0)
        if response.status_code < 500:
            return CheckResult(name, "ok", f"{name} reachable at {url}")
        return CheckResult(
            name,
            "fail",
            f"{name} returned HTTP {response.status_code}",
            f"Open {url} and inspect logs.",
        )
    except httpx.HTTPError:
        return CheckResult(
            name,
            "fail",
            f"{name} is not reachable at {url}",
            f"Start {name} and retry.",
        )


def check_env_file() -> CheckResult:
    path = PROJECT_DIR / ".env"
    if path.is_file():
        return CheckResult(".env", "ok", ".env exists")
    return CheckResult(
        ".env",
        "fail",
        ".env is missing",
        "Copy .env.template to .env and fill required values.",
    )


def check_workflow_file() -> CheckResult:
    path = PROJECT_DIR / "workflow.json"
    if path.is_file():
        return CheckResult("workflow", "ok", "workflow.json exists")
    return CheckResult(
        "workflow",
        "fail",
        "workflow.json is missing",
        "Run python scripts/build_workflow.py.",
    )


def collect_checks() -> list[CheckResult]:
    load_dotenv(PROJECT_DIR / ".env")
    n8n_url = os.environ.get("JOBS_FUNNEL_N8N_BASE", "http://localhost:5678")
    ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
    scoring_provider = os.environ.get("SCORING_PROVIDER", "codex_gpt55_high")
    review_provider = os.environ.get("SCORING_REVIEW_PROVIDER", "")
    codex_command = os.environ.get("SCORING_CODEX_CMD", "codex")
    claude_command = os.environ.get("SCORING_CLAUDE_CMD", "claude")
    checks = [
        check_env_file(),
        check_workflow_file(),
        check_command_available("docker", required=True),
        check_command_available("n8n", required=True),
        check_command_available(codex_command, required=scoring_provider.startswith("codex")),
        check_url("n8n", n8n_url),
    ]
    if os.environ.get("EMBEDDING_MODEL"):
        checks.append(check_url("ollama", ollama_url))
    if review_provider.startswith("claude") or scoring_provider.startswith("claude"):
        checks.append(check_command_available(claude_command, required=True))
    return checks


def exit_code(checks: list[CheckResult]) -> int:
    return 1 if any(check.status == "fail" for check in checks) else 0


def main() -> int:
    checks = collect_checks()
    for check in checks:
        for line in check.lines():
            print(line)
    return exit_code(checks)


if __name__ == "__main__":
    raise SystemExit(main())

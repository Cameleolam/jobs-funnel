#!/usr/bin/env python3
"""Few-shot calibration retrieval for scoring."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
_DOTENV_LOADED = False


def _load_env() -> None:
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    load_dotenv(ENV_PATH)
    _DOTENV_LOADED = True


def _env_int(name: str, default: int) -> int:
    _load_env()
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


def _env_float(name: str, default: float) -> float:
    _load_env()
    try:
        value = float(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


def calibration_k() -> int:
    return _env_int("CALIBRATION_K", 3)


def calibration_min_pool() -> int:
    return _env_int("CALIBRATION_MIN_POOL", 3)


def calibration_k_batch() -> int:
    return _env_int("CALIBRATION_K_BATCH", 6)


def weights() -> dict[str, float]:
    return {
        "offer": _env_float("WEIGHT_OFFER", 1.5),
        "interview": _env_float("WEIGHT_INTERVIEW", 1.4),
        "applied": _env_float("WEIGHT_APPLIED", 1.2),
        "dismiss_note": _env_float("WEIGHT_DISMISS_NOTE", 1.2),
        "dismiss": _env_float("WEIGHT_DISMISS", 0.8),
        "interested": _env_float("WEIGHT_INTERESTED", 0.7),
    }


def _short_text(value: Any, limit: int = 200) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def format_anchor(anchor: dict[str, Any], index: int) -> str:
    title = str(anchor.get("title") or "Untitled")
    company = str(anchor.get("company") or "Unknown")
    score = anchor.get("fit_score")
    label = str(anchor.get("calibration_label") or anchor.get("user_status") or "unknown")
    outcome = f"Score: {score if score is not None else '?'} -> {label}"
    if anchor.get("reached_interview"):
        outcome += " -> reached interview"
    if anchor.get("received_offer"):
        outcome += " -> received offer"

    note = _short_text(anchor.get("notes"))
    if note:
        rationale = f"Your note: {note}"
    else:
        rationale = f"Your prior reasoning: {_short_text(anchor.get('reasoning'))}"

    return f'{index}. "{title} @ {company}"\n   {outcome}\n   {rationale}'


def format_calibration_block(anchors: list[dict[str, Any]]) -> str:
    if not anchors:
        return ""
    lines = [
        "CALIBRATION - here's how you handled similar jobs in the past.",
        "Use these as calibration anchors, not as hard rules.",
        "",
    ]
    lines.extend(format_anchor(anchor, i) for i, anchor in enumerate(anchors, start=1))
    return "\n\n".join(lines)


def merge_batch_anchors(anchor_groups: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    best_by_id: dict[int, dict[str, Any]] = {}
    for group in anchor_groups:
        for anchor in group:
            try:
                anchor_id = int(anchor["id"])
            except (KeyError, TypeError, ValueError):
                continue
            current = best_by_id.get(anchor_id)
            if current is None or float(anchor.get("weighted_score") or 0) > float(current.get("weighted_score") or 0):
                best_by_id[anchor_id] = dict(anchor)

    ordered = sorted(
        best_by_id.values(),
        key=lambda a: float(a.get("weighted_score") or 0),
        reverse=True,
    )
    return ordered[: calibration_k_batch()]

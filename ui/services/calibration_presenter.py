"""Presentation helpers for calibration proposal metrics."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def proposal_summary_lines(proposal: Mapping[str, Any]) -> list[str]:
    metrics = _mapping(proposal.get("metrics"))
    proposal_metrics = _mapping(metrics.get("proposal"))
    evidence = _mapping(proposal_metrics.get("evidence"))
    guards = _mapping(proposal_metrics.get("guards"))
    rationale = _mapping(proposal.get("rationale"))
    lines: list[str] = []

    false_positives = _count(evidence.get("false_positives"))
    false_negatives = _count(evidence.get("false_negatives"))

    if false_positives:
        lines.append(f"You dismissed {false_positives} high-scored jobs.")
    if false_negatives:
        lines.append(f"You pursued {false_negatives} low-scored jobs.")

    review_band = str(rationale.get("review_band") or "")
    if "lowered review_low" in review_band:
        lines.append("The proposal widens review toward lower scores.")
    elif "raised review_high" in review_band:
        lines.append("The proposal widens review toward higher scores.")
    elif "expanded review band" in review_band:
        lines.append("The proposal widens review in both directions.")

    if guards:
        projected = guards.get("projected_review_jobs", 0)
        cap = guards.get("projected_review_cap", 0)
        lines.append(f"Projected review volume stays at {projected} of {cap} allowed jobs.")

    return lines or ["Not enough stored proposal metrics to explain this row."]

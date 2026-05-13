from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Optional, TypedDict


Confidence = Literal["low", "medium", "high"]
FinalDecision = Literal["apply", "maybe", "skip", "pending_review"]


class FilterState(TypedDict, total=False):
    job: dict[str, Any]
    job_embedding_calibration: Optional[list[float]]
    similar_decisions: list[dict[str, Any]]
    relevant_cv_bullets: list[dict[str, Any]]
    assessment: dict[str, Any]
    raw_score: Optional[float]
    confidence: Optional[Confidence]
    explanation: Optional[str]
    cv_variant: Optional[str]
    critique_count: int
    final_decision: Optional[FinalDecision]
    needs_human_review: bool
    scored_uncalibrated: bool
    system_prompt: str
    root: Path
    config: dict[str, Any]
    base_provider: Any
    review_provider: Any


def has_calibration(job: dict[str, Any]) -> bool:
    return job.get("_embedding_calibration_present", True) is not False


def initial_state(job: dict[str, Any]) -> FilterState:
    return {
        "job": job,
        "job_embedding_calibration": None,
        "similar_decisions": [],
        "relevant_cv_bullets": [],
        "assessment": {},
        "raw_score": None,
        "confidence": None,
        "explanation": None,
        "cv_variant": None,
        "critique_count": 0,
        "final_decision": None,
        "needs_human_review": False,
        "scored_uncalibrated": not has_calibration(job),
    }

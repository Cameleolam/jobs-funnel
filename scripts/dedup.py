#!/usr/bin/env python3
"""Tiered semantic dedup using pgvector first and Claude only for borderline pairs."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


THRESHOLD_CERTAIN = float(os.environ.get("DEDUP_THRESHOLD_CERTAIN", "0.95"))
THRESHOLD_REVIEW = float(os.environ.get("DEDUP_THRESHOLD_REVIEW", "0.85"))


@dataclass(frozen=True)
class DedupDecision:
    new_id: int
    existing_id: int | None
    decision_path: str
    similarity: float | None = None
    confidence: str = "none"
    reason: str = ""

    def to_pair(self) -> dict[str, Any] | None:
        if self.existing_id is None:
            return None
        return {
            "new_id": self.new_id,
            "existing_id": self.existing_id,
            "confidence": self.confidence,
            "reason": self.reason[:200],
            "decision_path": self.decision_path,
            "similarity": self.similarity,
        }


def classify_similarity(similarity: float | None) -> str:
    if similarity is None:
        return "no_match"
    if similarity >= THRESHOLD_CERTAIN:
        return "vector_certain"
    if similarity < THRESHOLD_REVIEW:
        return "vector_clear"
    return "claude_review"

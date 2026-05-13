from __future__ import annotations

from typing import Any

from scripts import retrieval
from scripts.graph.state import FilterState, has_calibration
from scripts.llm.parsing import loads_jsonish
from scripts.llm.providers import review_band
from scripts.llm.types import ProviderRequest
from scripts.scoring import build_review_prompt, build_user_prompt


def retrieve_decisions_node(state: FilterState) -> FilterState:
    out = dict(state)
    job = out["job"]
    out["similar_decisions"] = (
        retrieval.retrieve_similar_decisions(job) if has_calibration(job) else []
    )
    return out


def retrieve_cv_context_node(state: FilterState) -> FilterState:
    out = dict(state)
    out["relevant_cv_bullets"] = []
    return out


def _pending_review_assessment(blocker: str, reasoning: str) -> dict[str, Any]:
    return {
        "fit_score": None,
        "decision": "pending_review",
        "cv_variant": "software",
        "hard_blockers": [blocker],
        "soft_gaps": [],
        "strong_matches": [],
        "reasoning": reasoning,
        "priority_notes": None,
        "confidence": "medium",
        "needs_human_review": True,
    }


def _system_prompt_with_state_context(state: FilterState) -> str:
    prompt = state.get("system_prompt", "")
    block = retrieval.format_calibration_block(state.get("similar_decisions") or [])
    if block:
        return prompt.rstrip() + "\n\n" + block
    return prompt


def _parse_assessment(text: str) -> dict[str, Any]:
    try:
        parsed = loads_jsonish(text)
    except Exception:
        return _pending_review_assessment(
            "Scoring provider returned unreadable assessment",
            "The provider response could not be parsed as an assessment object.",
        )

    if isinstance(parsed, dict):
        return parsed
    return _pending_review_assessment(
        "Scoring provider returned non-object assessment",
        f"Invalid assessment type: {type(parsed).__name__}",
    )


def _score_value(assessment: dict[str, Any]) -> int | None:
    try:
        return int(assessment.get("fit_score"))
    except (TypeError, ValueError):
        return None


def _apply_base_metadata(assessment: dict[str, Any], provider: Any) -> dict[str, Any]:
    out = dict(assessment)
    out["scoring_provider"] = provider.provider_key
    out["scoring_model"] = provider.model
    return out


def _stamp_state_from_assessment(
    state: FilterState,
    assessment: dict[str, Any],
) -> FilterState:
    out = dict(state)
    stamped = dict(assessment)
    needs_human_review = (
        bool(out.get("needs_human_review", False))
        or stamped.get("needs_human_review") is True
        or stamped.get("decision") == "pending_review"
    )
    if out.get("scored_uncalibrated"):
        stamped["scored_uncalibrated"] = True
    out["assessment"] = stamped
    out["raw_score"] = _score_value(stamped)
    out["confidence"] = stamped.get("confidence")
    out["explanation"] = stamped.get("explanation") or stamped.get("reasoning")
    out["cv_variant"] = stamped.get("cv_variant")
    out["needs_human_review"] = needs_human_review
    return out


def score_node(state: FilterState) -> FilterState:
    provider = state["base_provider"]
    response = provider.generate(
        ProviderRequest(
            system_prompt=_system_prompt_with_state_context(state),
            user_prompt=build_user_prompt(state["job"], is_batch=False),
            cwd=state["root"],
        )
    )
    assessment = _apply_base_metadata(_parse_assessment(response.text), provider)
    return _stamp_state_from_assessment(state, assessment)


def grade_route(state: FilterState) -> str:
    score = state.get("raw_score")
    if score is None:
        return "flag_human"
    low, high = review_band()
    if low <= score <= high and int(state.get("critique_count", 0)) < 1:
        return "critique"
    if low <= score <= high:
        return "flag_human"
    return "select_cv"


def self_critique_node(state: FilterState) -> FilterState:
    provider = state.get("review_provider")
    if provider is None:
        return flag_human_node(state)

    base = dict(state["assessment"])
    response = provider.generate(
        ProviderRequest(
            system_prompt=_system_prompt_with_state_context(state),
            user_prompt=build_review_prompt(state["job"], base),
            cwd=state["root"],
        )
    )
    reviewed = dict(base)
    reviewed.update(_parse_assessment(response.text))
    reviewed["scoring_provider"] = base.get("scoring_provider")
    reviewed["scoring_model"] = base.get("scoring_model")
    reviewed["review_provider"] = provider.provider_key
    reviewed["review_model"] = provider.model
    reviewed["base_fit_score"] = base.get("fit_score")
    reviewed["base_decision"] = base.get("decision")

    out = dict(state)
    out["critique_count"] = int(state.get("critique_count", 0)) + 1
    return _stamp_state_from_assessment(out, reviewed)


def flag_human_node(state: FilterState) -> FilterState:
    out = dict(state)
    assessment = dict(out.get("assessment") or {})
    explanation = (
        out.get("explanation")
        or assessment.get("explanation")
        or assessment.get("reasoning")
        or "Assessment requires human review."
    )
    assessment["decision"] = "pending_review"
    assessment["needs_human_review"] = True
    assessment["explanation"] = explanation
    assessment["confidence"] = assessment.get("confidence") or "medium"
    assessment["critique_count"] = int(out.get("critique_count", 0))
    out["assessment"] = assessment
    out["needs_human_review"] = True
    out["final_decision"] = "pending_review"
    out["explanation"] = explanation
    out["confidence"] = assessment["confidence"]
    return out


def select_cv_node(state: FilterState) -> FilterState:
    out = dict(state)
    decision = str((out.get("assessment") or {}).get("decision") or "").upper()
    out["final_decision"] = {
        "PASS": "apply",
        "MAYBE": "maybe",
        "SKIP": "skip",
    }.get(decision, "pending_review" if decision.lower() == "pending_review" else None)
    return out


def persist_node(state: FilterState) -> FilterState:
    out = dict(state)
    assessment = dict(out.get("assessment") or {})
    needs_human_review = (
        bool(out.get("needs_human_review", False))
        or assessment.get("needs_human_review") is True
        or assessment.get("decision") == "pending_review"
    )
    assessment["needs_human_review"] = needs_human_review
    assessment["explanation"] = (
        assessment.get("explanation")
        or out.get("explanation")
        or assessment.get("reasoning")
    )
    assessment["confidence"] = assessment.get("confidence") or out.get("confidence") or "medium"
    assessment["critique_count"] = int(out.get("critique_count", 0))
    if out.get("scored_uncalibrated"):
        assessment["scored_uncalibrated"] = True
    out["assessment"] = assessment
    out["needs_human_review"] = needs_human_review
    return out

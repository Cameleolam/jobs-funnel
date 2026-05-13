from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from scripts import retrieval
from scripts.lib.job_text import normalize_job_for_llm
from scripts.llm.parsing import coerce_assessment_list, fallback_assessment, loads_jsonish
from scripts.llm.providers import provider_from_key, review_band
from scripts.llm.types import ProviderRequest


def _has_calibration(job: dict[str, Any]) -> bool:
    return job.get("_embedding_calibration_present", True)


def normalize_filter_input(parsed_input: Any) -> Any:
    if isinstance(parsed_input, list):
        return [
            normalize_job_for_llm(job) if isinstance(job, dict) else job
            for job in parsed_input
        ]
    if isinstance(parsed_input, dict):
        return normalize_job_for_llm(parsed_input)
    return parsed_input


def _calibration_anchor_groups(parsed_input: Any, is_batch: bool) -> list[list[dict[str, Any]]]:
    jobs = parsed_input if is_batch else [parsed_input]
    groups = []
    for job in jobs:
        if not isinstance(job, dict) or not _has_calibration(job):
            continue
        anchors = retrieval.retrieve_similar_decisions(job)
        if anchors:
            groups.append(anchors)
    return groups


def _system_prompt_with_calibration(system_prompt: str, parsed_input: Any, is_batch: bool) -> str:
    groups = _calibration_anchor_groups(parsed_input, is_batch)
    if not groups:
        return system_prompt
    anchors = retrieval.merge_batch_anchors(groups)
    block = retrieval.format_calibration_block(anchors)
    if not block:
        return system_prompt
    return system_prompt.rstrip() + "\n\n" + block


def build_user_prompt(prompt_input: Any, is_batch: bool) -> str:
    normalized = normalize_filter_input(prompt_input)
    if is_batch:
        lines = [f"Evaluate these {len(normalized)} job postings:", ""]
        for i, job in enumerate(normalized, start=1):
            lines.append(f"--- JOB {i} ---")
            lines.append(json.dumps(job, ensure_ascii=False))
            lines.append("")
        return "\n".join(lines)
    return f"Evaluate this job posting:\n\n{json.dumps(normalized, ensure_ascii=False)}"


def provider_keys_from_env() -> tuple[str, str | None]:
    base_key = os.environ.get("SCORING_PROVIDER", "claude_sonnet").strip() or "claude_sonnet"
    review_key = os.environ.get("SCORING_REVIEW_PROVIDER", "").strip() or None
    return base_key, review_key


def should_review(assessment: dict[str, Any]) -> bool:
    try:
        score = int(assessment.get("fit_score"))
    except (TypeError, ValueError):
        return False
    low, high = review_band()
    return low <= score <= high


def _metadata(provider_key: str, model: str) -> dict[str, str]:
    return {
        "scoring_provider": provider_key,
        "scoring_model": model,
    }


def _apply_metadata(assessment: dict[str, Any], provider_key: str, model: str) -> dict[str, Any]:
    out = dict(assessment)
    out.update(_metadata(provider_key, model))
    return out


def _preserve_review_diagnostics(reviewed: dict[str, Any], base_assessment: dict[str, Any]) -> None:
    for key in ("scored_uncalibrated", "error_code"):
        if key in base_assessment:
            reviewed[key] = base_assessment[key]
    if base_assessment.get("error_code") == "BATCH_PADDING" and "priority_notes" in base_assessment:
        reviewed["priority_notes"] = base_assessment["priority_notes"]


def _stamp_uncalibrated(assessment: Any, parsed_input: Any, is_batch: bool) -> Any:
    if is_batch:
        rows = assessment if isinstance(assessment, list) else [assessment]
        originals = parsed_input if isinstance(parsed_input, list) else [parsed_input]
        for i, original in enumerate(originals):
            if i < len(rows) and isinstance(rows[i], dict) and isinstance(original, dict):
                if not _has_calibration(original):
                    rows[i]["scored_uncalibrated"] = True
        return rows
    if isinstance(assessment, dict) and isinstance(parsed_input, dict) and not _has_calibration(parsed_input):
        assessment["scored_uncalibrated"] = True
    return assessment


def build_review_prompt(job: dict[str, Any], base_assessment: dict[str, Any]) -> str:
    return (
        "Review this borderline scoring decision.\n"
        "Use the same scoring rubric and return one final JSON assessment object. "
        "You may keep the original assessment or revise it. "
        "Do not include markdown fences or commentary outside JSON.\n\n"
        "<JOB>\n"
        f"{json.dumps(job, ensure_ascii=False)}\n"
        "</JOB>\n\n"
        "<BASE_ASSESSMENT>\n"
        f"{json.dumps(base_assessment, ensure_ascii=False)}\n"
        "</BASE_ASSESSMENT>\n"
    )


def _review_one(
    job: dict[str, Any],
    base_assessment: dict[str, Any],
    system_prompt: str,
    root: Path,
    review_provider: Any,
) -> dict[str, Any]:
    response = review_provider.generate(
        ProviderRequest(
            system_prompt=system_prompt,
            user_prompt=build_review_prompt(job, base_assessment),
            cwd=root,
        )
    )
    parsed = loads_jsonish(response.text)
    if isinstance(parsed, list):
        parsed = parsed[0] if parsed else {}
    if not isinstance(parsed, dict):
        return base_assessment
    reviewed = dict(parsed)
    reviewed["scoring_provider"] = base_assessment.get("scoring_provider")
    reviewed["scoring_model"] = base_assessment.get("scoring_model")
    reviewed["review_provider"] = review_provider.provider_key
    reviewed["review_model"] = review_provider.model
    reviewed["base_fit_score"] = base_assessment.get("fit_score")
    reviewed["base_decision"] = base_assessment.get("decision")
    _preserve_review_diagnostics(reviewed, base_assessment)
    return reviewed


def _apply_review(
    assessment: Any,
    prompt_input: Any,
    system_prompt: str,
    root: Path,
    review_provider: Any | None,
) -> Any:
    if review_provider is None:
        return assessment
    max_reviews = int(os.environ.get("SCORING_REVIEW_MAX_PER_BATCH", "8"))
    reviewed_count = 0

    if isinstance(assessment, list):
        jobs = prompt_input if isinstance(prompt_input, list) else [prompt_input]
        out = []
        for i, item in enumerate(assessment):
            if (
                reviewed_count < max_reviews
                and isinstance(item, dict)
                and i < len(jobs)
                and isinstance(jobs[i], dict)
                and should_review(item)
                and not item.get("error_code")
            ):
                try:
                    out.append(_review_one(jobs[i], item, system_prompt, root, review_provider))
                    reviewed_count += 1
                except Exception:
                    out.append(item)
            else:
                out.append(item)
        return out

    if (
        isinstance(assessment, dict)
        and isinstance(prompt_input, dict)
        and should_review(assessment)
        and not assessment.get("error_code")
    ):
        try:
            return _review_one(prompt_input, assessment, system_prompt, root, review_provider)
        except Exception:
            return assessment
    return assessment


def _parse_failure(response: Any, parsed_input: Any, is_batch: bool) -> Any:
    fallback = fallback_assessment(
        blocker="Scoring provider response parse error",
        reasoning=f"Parse error: {response.text[:200]}",
        error_code="PARSE_FAIL",
    )
    fallback = _apply_metadata(fallback, response.provider_key, response.model)
    if is_batch:
        return [dict(fallback) for _ in parsed_input]
    return fallback


def score_input(
    parsed_input: Any,
    system_prompt: str,
    config: dict[str, Any],
    root: Path,
    base_provider: Any | None = None,
    review_provider: Any | None = None,
) -> Any:
    is_batch = isinstance(parsed_input, list)
    prompt_input = normalize_filter_input(parsed_input)
    system_prompt = _system_prompt_with_calibration(system_prompt, prompt_input, is_batch)
    user_prompt = build_user_prompt(prompt_input, is_batch)

    if base_provider is None:
        base_key, review_key = provider_keys_from_env()
        base_provider = provider_from_key(base_key, config)
        if review_provider is None and review_key:
            review_provider = provider_from_key(review_key, config)

    response = base_provider.generate(
        ProviderRequest(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            cwd=root,
        )
    )

    try:
        parsed = loads_jsonish(response.text)
    except Exception:
        assessment = _parse_failure(response, parsed_input, is_batch)
        return _stamp_uncalibrated(assessment, parsed_input, is_batch)

    if is_batch:
        assessment = coerce_assessment_list(parsed, len(parsed_input))
        assessment = [
            _apply_metadata(item, response.provider_key, response.model)
            for item in assessment
        ]
    elif isinstance(parsed, list):
        item = parsed[0] if parsed else fallback_assessment(
            blocker="Scoring provider returned empty assessment array",
            reasoning="Provider returned [] for a single job",
            error_code="PARSE_FAIL",
        )
        assessment = _apply_metadata(item, response.provider_key, response.model)
    elif isinstance(parsed, dict):
        assessment = _apply_metadata(parsed, response.provider_key, response.model)
    else:
        assessment = _apply_metadata(
            fallback_assessment(
                blocker="Scoring provider returned non-object assessment",
                reasoning=f"Invalid assessment type: {type(parsed).__name__}",
                error_code="PARSE_FAIL",
            ),
            response.provider_key,
            response.model,
        )

    assessment = _stamp_uncalibrated(assessment, parsed_input, is_batch)
    return _apply_review(assessment, prompt_input, system_prompt, root, review_provider)

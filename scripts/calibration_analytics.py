"""Outcome analytics and conservative calibration proposal rules."""
from __future__ import annotations

import math
from collections import Counter
from typing import Any, Mapping


BANDS = ("below_review", "review_band", "above_review", "unscored")
POSITIVE_STATUSES = {"applied", "in_process", "offer"}
PURSUED_STATUSES = POSITIVE_STATUSES | {"rejected"}
POSITIVE_WEIGHT_KEYS = (
    "weight_offer",
    "weight_interview",
    "weight_applied",
    "weight_interested",
)
DISMISSAL_WEIGHT_KEYS = ("weight_dismiss_note", "weight_dismiss")
MIN_WEIGHT = 0.4
MAX_WEIGHT = 2.0
REVIEW_VOLUME_CAP_RATE = 0.05


def score_band(score: Any, settings: Mapping[str, Any]) -> str:
    """Return the active review-band bucket for a fit score."""
    value = _coerce_score(score)
    review_low = float(settings["review_low"])
    review_high = float(settings["review_high"])

    return _score_band_for_value(value, review_low, review_high)


def _score_band_for_value(value: float | None, review_low: float, review_high: float) -> str:
    if value is None:
        return "unscored"
    if value < review_low:
        return "below_review"
    if value <= review_high:
        return "review_band"
    return "above_review"


def build_metrics(rows: list[Mapping[str, Any]], settings: Mapping[str, Any]) -> dict[str, Any]:
    """Aggregate review, outcome, score-band, provider, and example metrics."""
    sample_counts = {
        "jobs": len(rows),
        "review_decisions": 0,
        "downstream_outcomes": 0,
    }
    review_resolution_split: Counter[str] = Counter()
    score_bands = {band: _empty_counter() for band in BANDS}
    providers: dict[str, dict[str, int]] = {}
    false_positives: list[dict[str, Any]] = []
    false_negatives: list[dict[str, Any]] = []
    review_low = float(settings["review_low"])
    review_high = float(settings["review_high"])
    review_projection = {
        "current_review_jobs": 0,
        "lower_one_bucket_jobs": 0,
        "raise_one_bucket_jobs": 0,
        "cap_rate": REVIEW_VOLUME_CAP_RATE,
    }

    for row in rows:
        fit_score = _coerce_score(row.get("fit_score"))
        band = _score_band_for_value(fit_score, review_low, review_high)
        status = _normalized_status(row)
        pursued = _is_pursued(row)
        dismissed = status == "dismissed"
        rejected = status == "rejected"
        reviewed = bool(row.get("has_review_decision"))
        _update_review_projection(review_projection, fit_score, review_low, review_high)

        if reviewed:
            sample_counts["review_decisions"] += 1
            review_resolution_split[str(row.get("review_label") or "unlabeled")] += 1

        if pursued or dismissed or rejected:
            sample_counts["downstream_outcomes"] += 1

        band_counts = score_bands[band]
        band_counts["total"] += 1
        if pursued:
            band_counts["pursued"] += 1
        if dismissed:
            band_counts["dismissed"] += 1
        if rejected:
            band_counts["rejected"] += 1
        if reviewed:
            band_counts["review_decisions"] += 1

        provider_key = _provider_key(row)
        provider_counts = providers.setdefault(provider_key, _empty_provider_counter())
        provider_counts["jobs"] += 1
        if pursued:
            provider_counts["pursued"] += 1
        if dismissed:
            provider_counts["dismissed"] += 1
        if rejected:
            provider_counts["rejected"] += 1
        if reviewed:
            provider_counts["review_decisions"] += 1

        if band == "above_review" and dismissed:
            false_positives.append(_example(row))
        if band == "below_review" and pursued:
            false_negatives.append(_example(row))

    return {
        "sample_counts": sample_counts,
        "review": {"resolution_split": dict(review_resolution_split)},
        "score_bands": score_bands,
        "providers": providers,
        "examples": {
            "false_positives": false_positives,
            "false_negatives": false_negatives,
        },
        "review_projection": review_projection,
    }


def build_proposed_settings(
    metrics: Mapping[str, Any],
    active_settings: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a conservative settings proposal from observed outcomes."""
    proposed = dict(active_settings)
    sample_counts = metrics.get("sample_counts", {})
    review_decisions = int(sample_counts.get("review_decisions", 0) or 0)
    downstream_outcomes = int(sample_counts.get("downstream_outcomes", 0) or 0)
    ready = review_decisions >= 30 or downstream_outcomes >= 10

    if not ready:
        return {
            "confidence": "low",
            "proposed_settings": proposed,
            "rationale": {
                "review_band": "kept current band because sample size is low",
            },
        }

    examples = metrics.get("examples", {})
    false_positive_count = len(examples.get("false_positives", []) or [])
    false_negative_count = len(examples.get("false_negatives", []) or [])
    jobs = int(sample_counts.get("jobs", 0) or 0)
    score_bands = metrics.get("score_bands", {})
    current_review_jobs, lower_one_bucket_jobs, raise_one_bucket_jobs, cap_rate = _projection_values(
        metrics,
        score_bands,
        jobs,
    )
    review_cap = jobs * cap_rate
    projected_review_jobs = current_review_jobs
    review_band_rationale = "kept current band because proposal guard did not justify expansion"

    if false_negative_count >= 3:
        projected = projected_review_jobs + lower_one_bucket_jobs
        if _within_review_cap(projected, review_cap):
            proposed["review_low"] = max(0, int(proposed["review_low"]) - 1)
            projected_review_jobs = projected
            review_band_rationale = "lowered review_low by 1 because false negatives reached threshold"

    if false_positive_count >= 5:
        projected = projected_review_jobs + raise_one_bucket_jobs
        if _within_review_cap(projected, review_cap):
            proposed["review_high"] = min(10, int(proposed["review_high"]) + 1)
            projected_review_jobs = projected
            if proposed["review_low"] != active_settings.get("review_low"):
                review_band_rationale = "expanded review band because false positives and false negatives reached thresholds"
            else:
                review_band_rationale = "raised review_high by 1 because false positives reached threshold"

    if false_negative_count:
        for key in POSITIVE_WEIGHT_KEYS:
            _increment_weight(proposed, key)

    if false_positive_count:
        for key in DISMISSAL_WEIGHT_KEYS:
            _increment_weight(proposed, key)

    confidence = "high" if downstream_outcomes >= 30 else "medium"
    return {
        "confidence": confidence,
        "proposed_settings": proposed,
        "rationale": {
            "review_band": review_band_rationale,
            "weights": _weight_rationale(false_positive_count, false_negative_count),
        },
        "guards": {
            "projected_review_jobs": projected_review_jobs,
            "projected_review_cap": review_cap,
            "projected_review_cap_rate": cap_rate,
        },
        "evidence": {
            "false_positives": false_positive_count,
            "false_negatives": false_negative_count,
        },
    }


def _empty_counter() -> dict[str, int]:
    return {
        "total": 0,
        "pursued": 0,
        "dismissed": 0,
        "rejected": 0,
        "review_decisions": 0,
    }


def _empty_provider_counter() -> dict[str, int]:
    return {
        "jobs": 0,
        "pursued": 0,
        "dismissed": 0,
        "rejected": 0,
        "review_decisions": 0,
    }


def _normalized_status(row: Mapping[str, Any]) -> str | None:
    status = row.get("user_status")
    return str(status).strip().lower() if status is not None else None


def _is_pursued(row: Mapping[str, Any]) -> bool:
    return (
        _normalized_status(row) in PURSUED_STATUSES
        or bool(row.get("has_application"))
        or bool(row.get("has_interview"))
        or bool(row.get("has_offer_event"))
    )


def _provider_key(row: Mapping[str, Any]) -> str:
    provider = str(row.get("scoring_provider") or "unknown")
    model = str(row.get("scoring_model") or "unknown")
    return f"{provider}/{model}"


def _example(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "title": row.get("title"),
        "company": row.get("company"),
        "fit_score": row.get("fit_score"),
        "user_status": row.get("user_status"),
        "notes": row.get("notes"),
    }


def _within_review_cap(projected_review_jobs: int, review_cap: float) -> bool:
    return projected_review_jobs <= review_cap


def _coerce_score(score: Any) -> float | None:
    if score is None:
        return None
    try:
        value = float(score)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _update_review_projection(
    review_projection: dict[str, float],
    fit_score: float | None,
    review_low: float,
    review_high: float,
) -> None:
    if fit_score is None:
        return
    if review_low <= fit_score <= review_high:
        review_projection["current_review_jobs"] += 1
    elif review_low - 1 <= fit_score < review_low:
        review_projection["lower_one_bucket_jobs"] += 1
    elif review_high < fit_score <= review_high + 1:
        review_projection["raise_one_bucket_jobs"] += 1


def _projection_values(
    metrics: Mapping[str, Any],
    score_bands: Mapping[str, Any],
    jobs: int,
) -> tuple[int, int, int, float]:
    review_projection = metrics.get("review_projection")
    review_band_total = _counter_total(score_bands, "review_band")
    below_total = _counter_total(score_bands, "below_review", default=jobs + 1)
    above_total = _counter_total(score_bands, "above_review", default=jobs + 1)

    if isinstance(review_projection, Mapping):
        current_review_jobs = _nonnegative_int(
            review_projection.get("current_review_jobs"),
            review_band_total,
        )
        lower_one_bucket_jobs = _nonnegative_int(
            review_projection.get("lower_one_bucket_jobs"),
            below_total,
        )
        raise_one_bucket_jobs = _nonnegative_int(
            review_projection.get("raise_one_bucket_jobs"),
            above_total,
        )
        cap_rate = _positive_float(review_projection.get("cap_rate"), REVIEW_VOLUME_CAP_RATE)
    else:
        current_review_jobs = review_band_total
        lower_one_bucket_jobs = below_total
        raise_one_bucket_jobs = above_total
        cap_rate = REVIEW_VOLUME_CAP_RATE

    return current_review_jobs, lower_one_bucket_jobs, raise_one_bucket_jobs, cap_rate


def _counter_total(score_bands: Mapping[str, Any], band: str, default: int = 0) -> int:
    counts = score_bands.get(band, {})
    if not isinstance(counts, Mapping):
        return default
    return _nonnegative_int(counts.get("total"), default)


def _nonnegative_int(value: Any, default: int) -> int:
    try:
        out = int(value)
    except (TypeError, ValueError):
        return default
    return out if out >= 0 else default


def _positive_float(value: Any, default: float) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) and out > 0 else default


def _increment_weight(settings: dict[str, Any], key: str) -> None:
    if key not in settings:
        return
    value = float(settings[key]) + 0.1
    settings[key] = round(min(MAX_WEIGHT, max(MIN_WEIGHT, value)), 10)


def _weight_rationale(false_positive_count: int, false_negative_count: int) -> str:
    if false_positive_count and false_negative_count:
        return "increased positive and dismissal weights based on false negative and false positive evidence"
    if false_negative_count:
        return "increased positive weights based on false negative evidence"
    if false_positive_count:
        return "increased dismissal weights based on false positive evidence"
    return "kept weights because no false positive or false negative evidence was present"

from scripts import calibration_analytics as analytics
from scripts.calibration_settings import DEFAULT_SETTINGS


def _job(job_id, score, user_status=None, decision="PASS", provider="claude_sonnet", model="sonnet"):
    return {
        "id": job_id,
        "title": f"Job {job_id}",
        "company": "Acme",
        "fit_score": score,
        "decision": decision,
        "user_status": user_status,
        "scoring_provider": provider,
        "scoring_model": model,
        "review_provider": None,
        "review_model": None,
        "has_application": False,
        "has_interview": False,
        "has_offer_event": False,
        "has_review_decision": False,
        "review_label": None,
        "notes": None,
    }


def test_score_band_uses_active_review_band():
    settings = {**DEFAULT_SETTINGS, "review_low": 4, "review_high": 6}

    assert analytics.score_band(3, settings) == "below_review"
    assert analytics.score_band(4, settings) == "review_band"
    assert analytics.score_band(6, settings) == "review_band"
    assert analytics.score_band(7, settings) == "above_review"


def test_build_metrics_handles_null_missing_and_non_numeric_fit_score():
    settings = {**DEFAULT_SETTINGS, "review_low": 4, "review_high": 6}
    missing_score = _job(3, 8)
    del missing_score["fit_score"]
    rows = [
        _job(1, None),
        _job(2, "not-a-score"),
        missing_score,
        _job(4, 3.5),
        _job(5, 5),
        _job(6, 6.5),
        _job(7, 7),
    ]

    metrics = analytics.build_metrics(rows, settings)

    assert analytics.score_band(None, settings) == "unscored"
    assert analytics.score_band("not-a-score", settings) == "unscored"
    assert metrics["score_bands"]["unscored"]["total"] == 3
    assert metrics["review_projection"] == {
        "current_review_jobs": 1,
        "lower_one_bucket_jobs": 1,
        "raise_one_bucket_jobs": 2,
        "cap_rate": 0.05,
    }


def test_build_metrics_counts_reviews_outcomes_and_examples():
    rows = [
        {**_job(1, 8, "dismissed"), "notes": "too frontend"},
        {**_job(2, 3, "applied"), "has_interview": True},
        {**_job(3, 5, "interested"), "has_review_decision": True, "review_label": "Reviewed: maybe"},
        {**_job(4, 9, "offer"), "has_offer_event": True},
    ]

    metrics = analytics.build_metrics(rows, {**DEFAULT_SETTINGS, "review_low": 4, "review_high": 6})

    assert metrics["sample_counts"]["jobs"] == 4
    assert metrics["sample_counts"]["review_decisions"] == 1
    assert metrics["sample_counts"]["downstream_outcomes"] == 3
    assert metrics["review"]["resolution_split"]["Reviewed: maybe"] == 1
    assert metrics["score_bands"]["above_review"]["dismissed"] == 1
    assert metrics["score_bands"]["below_review"]["pursued"] == 1
    assert metrics["examples"]["false_positives"][0]["id"] == 1
    assert metrics["examples"]["false_negatives"][0]["id"] == 2
    assert metrics["providers"]["claude_sonnet/sonnet"]["jobs"] == 4


def test_build_metrics_tracks_rejected_separately_from_dismissed():
    metrics = analytics.build_metrics(
        [
            _job(1, 8, "rejected"),
            _job(2, 9, "dismissed"),
        ],
        DEFAULT_SETTINGS,
    )

    assert metrics["sample_counts"]["downstream_outcomes"] == 2
    assert metrics["score_bands"]["above_review"]["rejected"] == 1
    assert metrics["score_bands"]["above_review"]["dismissed"] == 1
    assert [job["id"] for job in metrics["examples"]["false_positives"]] == [2]


def test_build_metrics_counts_rejected_below_review_as_pursued_false_negative():
    metrics = analytics.build_metrics(
        [_job(1, 3, "rejected")],
        DEFAULT_SETTINGS,
    )

    assert metrics["sample_counts"]["downstream_outcomes"] == 1
    assert metrics["score_bands"]["below_review"]["pursued"] == 1
    assert metrics["score_bands"]["below_review"]["rejected"] == 1
    assert metrics["score_bands"]["below_review"]["dismissed"] == 0
    assert [job["id"] for job in metrics["examples"]["false_negatives"]] == [1]


def test_proposal_keeps_settings_when_low_confidence():
    metrics = {
        "sample_counts": {"jobs": 500, "review_decisions": 1, "downstream_outcomes": 2},
        "examples": {"false_positives": [], "false_negatives": []},
        "score_bands": {
            "below_review": {"total": 100, "pursued": 0, "dismissed": 0},
            "review_band": {"total": 20, "pursued": 0, "dismissed": 0},
            "above_review": {"total": 380, "pursued": 2, "dismissed": 0},
        },
    }

    proposal = analytics.build_proposed_settings(metrics, DEFAULT_SETTINGS)

    assert proposal["confidence"] == "low"
    assert proposal["proposed_settings"] == DEFAULT_SETTINGS
    assert proposal["rationale"]["review_band"] == "kept current band because sample size is low"


def test_proposal_adjusts_weights_for_false_positive_and_negative_evidence():
    metrics = {
        "sample_counts": {"jobs": 300, "review_decisions": 35, "downstream_outcomes": 12},
        "examples": {
            "false_positives": [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}, {"id": 5}],
            "false_negatives": [{"id": 6}, {"id": 7}, {"id": 8}],
        },
        "score_bands": {
            "below_review": {"total": 80, "pursued": 3, "dismissed": 0},
            "review_band": {"total": 10, "pursued": 2, "dismissed": 2},
            "above_review": {"total": 210, "pursued": 7, "dismissed": 5},
        },
        "review_projection": {
            "current_review_jobs": 10,
            "lower_one_bucket_jobs": 3,
            "raise_one_bucket_jobs": 1,
            "cap_rate": 0.05,
        },
    }

    proposal = analytics.build_proposed_settings(metrics, DEFAULT_SETTINGS)

    assert proposal["confidence"] in ("medium", "high")
    assert proposal["proposed_settings"]["weight_applied"] == 1.3
    assert proposal["proposed_settings"]["weight_dismiss"] == 0.9
    assert proposal["proposed_settings"]["review_low"] == 3


def test_proposal_blocks_expansion_when_exact_bucket_exceeds_volume_cap():
    metrics = {
        "sample_counts": {"jobs": 100, "review_decisions": 30, "downstream_outcomes": 10},
        "examples": {"false_positives": [], "false_negatives": [{"id": 1}, {"id": 2}, {"id": 3}]},
        "score_bands": {
            "below_review": {"total": 40, "pursued": 3, "dismissed": 0},
            "review_band": {"total": 0, "pursued": 0, "dismissed": 0},
            "above_review": {"total": 60, "pursued": 7, "dismissed": 0},
        },
        "review_projection": {
            "current_review_jobs": 0,
            "lower_one_bucket_jobs": 6,
            "raise_one_bucket_jobs": 0,
            "cap_rate": 0.05,
        },
    }

    proposal = analytics.build_proposed_settings(metrics, DEFAULT_SETTINGS)

    assert proposal["proposed_settings"]["review_low"] == DEFAULT_SETTINGS["review_low"]
    assert proposal["guards"]["projected_review_jobs"] == 0


def test_proposal_allows_expansion_when_exact_bucket_stays_within_volume_cap():
    metrics = {
        "sample_counts": {"jobs": 100, "review_decisions": 30, "downstream_outcomes": 10},
        "examples": {"false_positives": [], "false_negatives": [{"id": 1}, {"id": 2}, {"id": 3}]},
        "score_bands": {
            "below_review": {"total": 40, "pursued": 3, "dismissed": 0},
            "review_band": {"total": 2, "pursued": 0, "dismissed": 0},
            "above_review": {"total": 58, "pursued": 7, "dismissed": 0},
        },
        "review_projection": {
            "current_review_jobs": 2,
            "lower_one_bucket_jobs": 2,
            "raise_one_bucket_jobs": 0,
            "cap_rate": 0.05,
        },
    }

    proposal = analytics.build_proposed_settings(metrics, DEFAULT_SETTINGS)

    assert proposal["proposed_settings"]["review_low"] == 3
    assert proposal["guards"]["projected_review_jobs"] == 4


def test_proposal_does_not_mutate_active_settings():
    active = {**DEFAULT_SETTINGS, "weight_applied": 1.95}
    metrics = {
        "sample_counts": {"jobs": 100, "review_decisions": 30, "downstream_outcomes": 10},
        "examples": {"false_positives": [], "false_negatives": [{"id": 1}]},
        "score_bands": {
            "below_review": {"total": 20, "pursued": 1, "dismissed": 0},
            "review_band": {"total": 5, "pursued": 0, "dismissed": 0},
            "above_review": {"total": 75, "pursued": 9, "dismissed": 0},
        },
    }

    proposal = analytics.build_proposed_settings(metrics, active)

    assert active["weight_applied"] == 1.95
    assert proposal["proposed_settings"]["weight_applied"] == 2.0

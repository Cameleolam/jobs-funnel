import json
from unittest.mock import MagicMock

import pytest

from scripts.llm.types import ProviderError, ProviderRequest, ProviderResponse
from scripts.scoring import (
    _system_prompt_with_calibration,
    build_review_prompt,
    build_user_prompt,
    provider_keys_from_env,
    score_input,
    should_review,
)


class FakeProvider:
    def __init__(self, provider_key, text):
        self.provider_key = provider_key
        self.model = provider_key + "-model"
        self.text = text
        self.requests = []

    def generate(self, request: ProviderRequest):
        self.requests.append(request)
        return ProviderResponse(
            provider_key=self.provider_key,
            model=self.model,
            text=self.text,
            stdout=self.text,
            stderr="",
            returncode=0,
            elapsed_seconds=0.01,
        )


class FailingProvider:
    provider_key = "failing"
    model = "failing-model"

    def __init__(self, exc):
        self.exc = exc
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        raise self.exc


def _assessment(score=8, decision="PASS", reasoning="ok"):
    return {
        "fit_score": score,
        "decision": decision,
        "cv_variant": "software",
        "hard_blockers": [],
        "soft_gaps": [],
        "strong_matches": ["Python"],
        "reasoning": reasoning,
        "priority_notes": None,
    }


def _anchor(title):
    return {
        "id": sum(ord(ch) for ch in title),
        "title": title,
        "company": "Acme",
        "fit_score": 80,
        "calibration_label": "applied",
        "notes": "useful anchor",
        "reasoning": "",
        "reached_interview": False,
        "received_offer": False,
        "weighted_score": 0.9,
    }


def test_build_user_prompt_uses_normalized_descriptions_and_removes_arbeitnow_footer():
    jobs = [
        {
            "title": "Backend Engineer",
            "description": "<p>Python &amp; APIs</p><p>Find more English Speaking Jobs in Germany on Arbeitnow</p>",
        }
    ]

    prompt = build_user_prompt(jobs, is_batch=True)

    assert "<p>" not in prompt
    assert "Python & APIs" in prompt
    assert "English Speaking Jobs in Germany" not in prompt


def test_system_prompt_with_calibration_returns_original_prompt_when_no_anchors(monkeypatch):
    monkeypatch.setattr("scripts.scoring.retrieval.retrieve_similar_decisions", lambda job: [])

    prompt = "".join(["BASE", " PROMPT"])
    job = {"title": "T", "_embedding_calibration_present": True}

    assert _system_prompt_with_calibration(prompt, job, is_batch=False) is prompt


def test_system_prompt_with_calibration_skips_retrieval_without_calibration_vector(monkeypatch):
    retrieve = MagicMock(return_value=[_anchor("Should Not Be Used")])
    monkeypatch.setattr("scripts.scoring.retrieval.retrieve_similar_decisions", retrieve)

    prompt = "BASE PROMPT"
    job = {"title": "T", "_embedding_calibration_present": False}

    assert _system_prompt_with_calibration(prompt, job, is_batch=False) is prompt
    retrieve.assert_not_called()


def test_system_prompt_with_calibration_merges_batch_anchors(monkeypatch):
    calls = []

    def fake_retrieve(job):
        calls.append(job["title"])
        return [_anchor("Historical " + job["title"])]

    monkeypatch.setattr("scripts.scoring.retrieval.retrieve_similar_decisions", fake_retrieve)
    monkeypatch.setattr(
        "scripts.scoring.retrieval.merge_batch_anchors",
        lambda groups: [anchor for group in groups for anchor in group],
    )

    prompt = _system_prompt_with_calibration(
        "BASE PROMPT",
        [
            {"title": "A", "_embedding_calibration_present": True},
            {"title": "B", "_embedding_calibration_present": True},
            {"title": "C", "_embedding_calibration_present": False},
        ],
        is_batch=True,
    )

    assert calls == ["A", "B"]
    assert "BASE PROMPT" in prompt
    assert "CALIBRATION - here's how you handled similar jobs in the past." in prompt
    assert "Historical A @ Acme" in prompt
    assert "Historical B @ Acme" in prompt
    assert "Historical C @ Acme" not in prompt


def test_score_input_passes_calibration_augmented_prompt_to_provider(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "scripts.scoring.retrieval.retrieve_similar_decisions",
        lambda job: [_anchor("Backend Engineer")],
    )
    base = FakeProvider("claude_sonnet", json.dumps(_assessment()))

    score_input(
        parsed_input={"title": "T", "description": "D", "_embedding_calibration_present": True},
        system_prompt="BASE PROMPT",
        config={},
        root=tmp_path,
        base_provider=base,
    )

    system_prompt = base.requests[0].system_prompt
    assert "BASE PROMPT" in system_prompt
    assert "CALIBRATION - here's how you handled similar jobs in the past." in system_prompt
    assert "Backend Engineer @ Acme" in system_prompt


def test_provider_keys_from_env_defaults_to_claude(monkeypatch):
    monkeypatch.delenv("SCORING_PROVIDER", raising=False)
    monkeypatch.delenv("SCORING_REVIEW_PROVIDER", raising=False)

    assert provider_keys_from_env() == ("claude_sonnet", None)


def test_provider_keys_from_env_accepts_base_and_review(monkeypatch):
    monkeypatch.setenv("SCORING_PROVIDER", "codex_gpt55_high")
    monkeypatch.setenv("SCORING_REVIEW_PROVIDER", "claude_sonnet")

    assert provider_keys_from_env() == ("codex_gpt55_high", "claude_sonnet")


def test_should_review_uses_inclusive_four_to_six(monkeypatch):
    monkeypatch.delenv("SCORING_REVIEW_LOW", raising=False)
    monkeypatch.delenv("SCORING_REVIEW_HIGH", raising=False)

    assert should_review({"fit_score": 3}) is False
    assert should_review({"fit_score": 4}) is True
    assert should_review({"fit_score": 6}) is True
    assert should_review({"fit_score": 7}) is False


def test_should_review_uses_float_scores_without_truncation(monkeypatch):
    monkeypatch.delenv("SCORING_REVIEW_LOW", raising=False)
    monkeypatch.delenv("SCORING_REVIEW_HIGH", raising=False)

    assert should_review({"fit_score": 6.0}) is True
    assert should_review({"fit_score": 6.9}) is False
    assert should_review({"fit_score": 3.9}) is False


def test_score_input_single_provider_returns_same_json_shape_with_metadata(monkeypatch, tmp_path):
    monkeypatch.setattr("scripts.scoring._system_prompt_with_calibration", lambda prompt, parsed, is_batch: prompt)
    base = FakeProvider("claude_sonnet", json.dumps(_assessment()))

    result = score_input(
        parsed_input={"title": "T", "description": "D", "_embedding_calibration_present": True},
        system_prompt="SYSTEM",
        config={"model": "claude-sonnet-4-6"},
        root=tmp_path,
        base_provider=base,
    )

    assert result == {
        "fit_score": 8,
        "decision": "PASS",
        "cv_variant": "software",
        "hard_blockers": [],
        "soft_gaps": [],
        "strong_matches": ["Python"],
        "reasoning": "ok",
        "priority_notes": None,
        "scoring_provider": "claude_sonnet",
        "scoring_model": "claude_sonnet-model",
    }
    assert base.requests[0].system_prompt == "SYSTEM"


def test_score_input_stamps_uncalibrated_for_missing_embedding(monkeypatch, tmp_path):
    monkeypatch.setattr("scripts.scoring._system_prompt_with_calibration", lambda prompt, parsed, is_batch: prompt)
    base = FakeProvider("claude_sonnet", json.dumps(_assessment(score=5, decision="MAYBE")))

    result = score_input(
        parsed_input={"title": "T", "description": "D", "_embedding_calibration_present": False},
        system_prompt="SYSTEM",
        config={},
        root=tmp_path,
        base_provider=base,
    )

    assert result["scored_uncalibrated"] is True


def test_score_input_pads_short_batch_response_with_batch_padding(monkeypatch, tmp_path):
    monkeypatch.setattr("scripts.scoring._system_prompt_with_calibration", lambda prompt, parsed, is_batch: prompt)
    base = FakeProvider("claude_sonnet", json.dumps([_assessment()]))

    result = score_input(
        parsed_input=[
            {"title": "A", "description": "D"},
            {"title": "B", "description": "D"},
        ],
        system_prompt="SYSTEM",
        config={},
        root=tmp_path,
        base_provider=base,
    )

    assert len(result) == 2
    assert result[0]["fit_score"] == 8
    assert result[1]["error_code"] == "BATCH_PADDING"
    assert result[1]["scoring_provider"] == "claude_sonnet"


def test_score_input_returns_parse_fail_fallback_with_metadata_for_bad_provider_json(monkeypatch, tmp_path):
    monkeypatch.setattr("scripts.scoring._system_prompt_with_calibration", lambda prompt, parsed, is_batch: prompt)
    base = FakeProvider("codex_gpt55_high", "not json")

    result = score_input(
        parsed_input={"title": "T", "description": "D"},
        system_prompt="SYSTEM",
        config={},
        root=tmp_path,
        base_provider=base,
    )

    assert result["fit_score"] == 0
    assert result["error_code"] == "PARSE_FAIL"
    assert result["scoring_provider"] == "codex_gpt55_high"
    assert result["scoring_model"] == "codex_gpt55_high-model"


def test_score_input_returns_parse_fail_fallback_per_batch_item(monkeypatch, tmp_path):
    monkeypatch.setattr("scripts.scoring._system_prompt_with_calibration", lambda prompt, parsed, is_batch: prompt)
    base = FakeProvider("codex_gpt55_high", "not json")

    result = score_input(
        parsed_input=[{"title": "A", "description": "D"}, {"title": "B", "description": "D"}],
        system_prompt="SYSTEM",
        config={},
        root=tmp_path,
        base_provider=base,
    )

    assert [item["error_code"] for item in result] == ["PARSE_FAIL", "PARSE_FAIL"]
    assert [item["scoring_provider"] for item in result] == ["codex_gpt55_high", "codex_gpt55_high"]


@pytest.mark.parametrize("provider_text", ["[null]", '["bad"]'])
def test_score_input_single_job_array_with_non_object_returns_parse_fail(provider_text, monkeypatch, tmp_path):
    monkeypatch.setattr("scripts.scoring._system_prompt_with_calibration", lambda prompt, parsed, is_batch: prompt)
    base = FakeProvider("codex_gpt55_high", provider_text)

    result = score_input(
        parsed_input={"title": "T", "description": "D"},
        system_prompt="SYSTEM",
        config={},
        root=tmp_path,
        base_provider=base,
    )

    assert result["fit_score"] == 0
    assert result["error_code"] == "PARSE_FAIL"
    assert result["scoring_provider"] == "codex_gpt55_high"
    assert result["scoring_model"] == "codex_gpt55_high-model"


def test_score_input_raises_provider_error_for_api_failure(tmp_path):
    base = FailingProvider(ProviderError("claude_sonnet", "boom", stderr="bad"))

    with pytest.raises(ProviderError):
        score_input(
            parsed_input={"title": "T", "description": "D"},
            system_prompt="SYSTEM",
            config={},
            root=tmp_path,
            base_provider=base,
        )


def test_build_review_prompt_includes_job_and_base_assessment():
    prompt = build_review_prompt(
        job={"title": "Python Engineer"},
        base_assessment={"fit_score": 6, "decision": "MAYBE", "reasoning": "borderline"},
    )

    assert "Review this borderline scoring decision." in prompt
    assert '"title": "Python Engineer"' in prompt
    assert '"fit_score": 6' in prompt


def test_score_input_uses_review_provider_for_borderline_preserving_base_metadata(monkeypatch, tmp_path):
    monkeypatch.setattr("scripts.scoring._system_prompt_with_calibration", lambda prompt, parsed, is_batch: prompt)
    base = FakeProvider(
        "claude_sonnet",
        json.dumps(
            {
                **_assessment(score=6, decision="MAYBE", reasoning="borderline"),
                "soft_gaps": ["frontend gap"],
            }
        ),
    )
    review = FakeProvider(
        "codex_gpt55_high",
        json.dumps(
            {
                **_assessment(score=7, decision="PASS", reasoning="reviewed upward"),
                "soft_gaps": ["frontend gap"],
            }
        ),
    )

    result = score_input(
        parsed_input={"title": "T", "description": "D"},
        system_prompt="SYSTEM",
        config={},
        root=tmp_path,
        base_provider=base,
        review_provider=review,
    )

    assert result["fit_score"] == 7
    assert result["decision"] == "PASS"
    assert result["scoring_provider"] == "claude_sonnet"
    assert result["scoring_model"] == "claude_sonnet-model"
    assert result["review_provider"] == "codex_gpt55_high"
    assert result["review_model"] == "codex_gpt55_high-model"
    assert result["base_fit_score"] == 6
    assert result["base_decision"] == "MAYBE"
    assert len(review.requests) == 1


def test_score_input_review_preserves_uncalibrated_stamp(monkeypatch, tmp_path):
    monkeypatch.setattr("scripts.scoring._system_prompt_with_calibration", lambda prompt, parsed, is_batch: prompt)
    base = FakeProvider(
        "claude_sonnet",
        json.dumps(_assessment(score=5, decision="MAYBE", reasoning="uncalibrated borderline")),
    )
    review = FakeProvider(
        "codex_gpt55_high",
        json.dumps(_assessment(score=7, decision="PASS", reasoning="reviewed pass")),
    )

    result = score_input(
        parsed_input={"title": "T", "description": "D", "_embedding_calibration_present": False},
        system_prompt="SYSTEM",
        config={},
        root=tmp_path,
        base_provider=base,
        review_provider=review,
    )

    assert result["fit_score"] == 7
    assert result["scored_uncalibrated"] is True
    assert result["review_provider"] == "codex_gpt55_high"
    assert result["review_model"] == "codex_gpt55_high-model"
    assert result["base_fit_score"] == 5
    assert result["base_decision"] == "MAYBE"


def test_score_input_partial_review_preserves_required_base_fields(monkeypatch, tmp_path):
    monkeypatch.setattr("scripts.scoring._system_prompt_with_calibration", lambda prompt, parsed, is_batch: prompt)
    base = FakeProvider(
        "claude_sonnet",
        json.dumps(
            {
                **_assessment(score=5, decision="MAYBE", reasoning="borderline"),
                "cv_variant": "fullstack",
                "hard_blockers": ["salary unclear"],
                "soft_gaps": ["some React"],
                "strong_matches": ["Python", "APIs"],
                "priority_notes": "Needs review",
            }
        ),
    )
    review = FakeProvider(
        "codex_gpt55_high",
        json.dumps({"fit_score": 7, "decision": "PASS", "reasoning": "reviewed upward"}),
    )

    result = score_input(
        parsed_input={"title": "T", "description": "D"},
        system_prompt="SYSTEM",
        config={},
        root=tmp_path,
        base_provider=base,
        review_provider=review,
    )

    assert result["fit_score"] == 7
    assert result["decision"] == "PASS"
    assert result["reasoning"] == "reviewed upward"
    assert result["cv_variant"] == "fullstack"
    assert result["hard_blockers"] == ["salary unclear"]
    assert result["soft_gaps"] == ["some React"]
    assert result["strong_matches"] == ["Python", "APIs"]
    assert result["priority_notes"] == "Needs review"
    assert result["review_provider"] == "codex_gpt55_high"
    assert result["review_model"] == "codex_gpt55_high-model"
    assert result["base_fit_score"] == 5
    assert result["base_decision"] == "MAYBE"


def test_review_provider_only_reviews_borderline_jobs(monkeypatch, tmp_path):
    monkeypatch.setattr("scripts.scoring._system_prompt_with_calibration", lambda prompt, parsed, is_batch: prompt)
    base = FakeProvider(
        "claude_sonnet",
        json.dumps(
            [
                _assessment(score=8, decision="PASS", reasoning="clear pass"),
                _assessment(score=5, decision="MAYBE", reasoning="borderline"),
                _assessment(score=2, decision="SKIP", reasoning="clear skip"),
            ]
        ),
    )
    review = FakeProvider(
        "codex_gpt55_high",
        json.dumps(_assessment(score=6, decision="MAYBE", reasoning="reviewed")),
    )

    result = score_input(
        parsed_input=[
            {"title": "A", "description": "D"},
            {"title": "B", "description": "D"},
            {"title": "C", "description": "D"},
        ],
        system_prompt="SYSTEM",
        config={},
        root=tmp_path,
        base_provider=base,
        review_provider=review,
    )

    assert result[0].get("review_provider") is None
    assert result[1]["review_provider"] == "codex_gpt55_high"
    assert result[2].get("review_provider") is None
    assert len(review.requests) == 1


def test_review_provider_respects_max_reviews(monkeypatch, tmp_path):
    monkeypatch.setenv("SCORING_REVIEW_MAX_PER_BATCH", "1")
    monkeypatch.setattr("scripts.scoring._system_prompt_with_calibration", lambda prompt, parsed, is_batch: prompt)
    base = FakeProvider(
        "claude_sonnet",
        json.dumps(
            [
                _assessment(score=5, decision="MAYBE", reasoning="borderline one"),
                _assessment(score=6, decision="MAYBE", reasoning="borderline two"),
            ]
        ),
    )
    review = FakeProvider(
        "codex_gpt55_high",
        json.dumps(_assessment(score=7, decision="PASS", reasoning="reviewed")),
    )

    result = score_input(
        parsed_input=[
            {"title": "A", "description": "D"},
            {"title": "B", "description": "D"},
        ],
        system_prompt="SYSTEM",
        config={},
        root=tmp_path,
        base_provider=base,
        review_provider=review,
    )

    assert result[0]["review_provider"] == "codex_gpt55_high"
    assert result[1].get("review_provider") is None
    assert len(review.requests) == 1


@pytest.mark.parametrize("max_reviews", ["", "not-a-number"])
def test_review_max_invalid_env_defaults_to_eight(monkeypatch, tmp_path, max_reviews):
    monkeypatch.setenv("SCORING_REVIEW_MAX_PER_BATCH", max_reviews)
    monkeypatch.setattr("scripts.scoring._system_prompt_with_calibration", lambda prompt, parsed, is_batch: prompt)
    base = FakeProvider(
        "claude_sonnet",
        json.dumps([_assessment(score=5, decision="MAYBE", reasoning="borderline")]),
    )
    review = FakeProvider(
        "codex_gpt55_high",
        json.dumps(_assessment(score=7, decision="PASS", reasoning="reviewed")),
    )

    result = score_input(
        parsed_input=[{"title": "A", "description": "D"}],
        system_prompt="SYSTEM",
        config={},
        root=tmp_path,
        base_provider=base,
        review_provider=review,
    )

    assert result[0]["review_provider"] == "codex_gpt55_high"
    assert len(review.requests) == 1


def test_review_max_negative_env_disables_reviews(monkeypatch, tmp_path):
    monkeypatch.setenv("SCORING_REVIEW_MAX_PER_BATCH", "-1")
    monkeypatch.setattr("scripts.scoring._system_prompt_with_calibration", lambda prompt, parsed, is_batch: prompt)
    base = FakeProvider(
        "claude_sonnet",
        json.dumps([_assessment(score=5, decision="MAYBE", reasoning="borderline")]),
    )
    review = FakeProvider(
        "codex_gpt55_high",
        json.dumps(_assessment(score=7, decision="PASS", reasoning="should not run")),
    )

    result = score_input(
        parsed_input=[{"title": "A", "description": "D"}],
        system_prompt="SYSTEM",
        config={},
        root=tmp_path,
        base_provider=base,
        review_provider=review,
    )

    assert result[0]["fit_score"] == 5
    assert result[0].get("review_provider") is None
    assert len(review.requests) == 0


def test_review_failure_keeps_base_assessment_and_records_error(monkeypatch, tmp_path):
    monkeypatch.setattr("scripts.scoring._system_prompt_with_calibration", lambda prompt, parsed, is_batch: prompt)
    base = FakeProvider(
        "claude_sonnet",
        json.dumps(_assessment(score=5, decision="MAYBE", reasoning="borderline")),
    )
    review = FailingProvider(ProviderError("codex_gpt55_high", "review failed"))

    result = score_input(
        parsed_input={"title": "T", "description": "D"},
        system_prompt="SYSTEM",
        config={},
        root=tmp_path,
        base_provider=base,
        review_provider=review,
    )

    assert result["fit_score"] == 5
    assert result["decision"] == "MAYBE"
    assert result["reasoning"] == "borderline"
    assert result.get("review_provider") is None
    assert result["review_error"] == "review failed"


def test_batch_review_failure_keeps_base_assessment_and_records_error(monkeypatch, tmp_path):
    monkeypatch.setattr("scripts.scoring._system_prompt_with_calibration", lambda prompt, parsed, is_batch: prompt)
    base = FakeProvider(
        "claude_sonnet",
        json.dumps(
            [
                _assessment(score=5, decision="MAYBE", reasoning="borderline"),
                _assessment(score=8, decision="PASS", reasoning="clear pass"),
            ]
        ),
    )
    review = FailingProvider(ProviderError("codex_gpt55_high", "batch review failed"))

    result = score_input(
        parsed_input=[
            {"title": "A", "description": "D"},
            {"title": "B", "description": "D"},
        ],
        system_prompt="SYSTEM",
        config={},
        root=tmp_path,
        base_provider=base,
        review_provider=review,
    )

    assert result[0]["fit_score"] == 5
    assert result[0]["decision"] == "MAYBE"
    assert result[0]["reasoning"] == "borderline"
    assert result[0].get("review_provider") is None
    assert result[0]["review_error"] == "batch review failed"
    assert result[1].get("review_error") is None


def test_review_max_counts_failed_attempts(monkeypatch, tmp_path):
    monkeypatch.setenv("SCORING_REVIEW_MAX_PER_BATCH", "1")
    monkeypatch.setattr("scripts.scoring._system_prompt_with_calibration", lambda prompt, parsed, is_batch: prompt)
    base = FakeProvider(
        "claude_sonnet",
        json.dumps(
            [
                _assessment(score=5, decision="MAYBE", reasoning="borderline one"),
                _assessment(score=6, decision="MAYBE", reasoning="borderline two"),
            ]
        ),
    )
    review = FailingProvider(ProviderError("codex_gpt55_high", "first review failed"))

    result = score_input(
        parsed_input=[
            {"title": "A", "description": "D"},
            {"title": "B", "description": "D"},
        ],
        system_prompt="SYSTEM",
        config={},
        root=tmp_path,
        base_provider=base,
        review_provider=review,
    )

    assert len(review.requests) == 1
    assert result[0]["fit_score"] == 5
    assert result[0]["decision"] == "MAYBE"
    assert result[0]["review_error"] == "first review failed"
    assert result[1]["fit_score"] == 6
    assert result[1]["decision"] == "MAYBE"
    assert result[1].get("review_provider") is None
    assert result[1].get("review_error") is None


def test_review_provider_skips_items_with_error_code(monkeypatch, tmp_path):
    monkeypatch.setattr("scripts.scoring._system_prompt_with_calibration", lambda prompt, parsed, is_batch: prompt)
    base_item = {
        **_assessment(score=5, decision="MAYBE", reasoning="parse fallback"),
        "error_code": "PARSE_FAIL",
    }
    base = FakeProvider("claude_sonnet", json.dumps([base_item]))
    review = FakeProvider(
        "codex_gpt55_high",
        json.dumps(_assessment(score=7, decision="PASS", reasoning="should not run")),
    )

    result = score_input(
        parsed_input=[{"title": "A", "description": "D"}],
        system_prompt="SYSTEM",
        config={},
        root=tmp_path,
        base_provider=base,
        review_provider=review,
    )

    assert len(review.requests) == 0
    assert result[0] == {
        **base_item,
        "scoring_provider": "claude_sonnet",
        "scoring_model": "claude_sonnet-model",
    }


def test_review_provider_skips_error_code_before_malformed_review_band(monkeypatch, tmp_path):
    monkeypatch.setenv("SCORING_REVIEW_LOW", "bad-low")
    monkeypatch.setattr("scripts.scoring._system_prompt_with_calibration", lambda prompt, parsed, is_batch: prompt)
    base_item = {
        **_assessment(score=5, decision="MAYBE", reasoning="parse fallback"),
        "error_code": "PARSE_FAIL",
    }
    base = FakeProvider("claude_sonnet", json.dumps([base_item]))
    review = FakeProvider(
        "codex_gpt55_high",
        json.dumps(_assessment(score=7, decision="PASS", reasoning="should not run")),
    )

    result = score_input(
        parsed_input=[{"title": "A", "description": "D"}],
        system_prompt="SYSTEM",
        config={},
        root=tmp_path,
        base_provider=base,
        review_provider=review,
    )

    assert len(review.requests) == 0
    assert result[0]["error_code"] == "PARSE_FAIL"
    assert result[0].get("review_provider") is None


def test_review_null_response_keeps_base_assessment_and_records_error(monkeypatch, tmp_path):
    monkeypatch.setattr("scripts.scoring._system_prompt_with_calibration", lambda prompt, parsed, is_batch: prompt)
    base = FakeProvider(
        "claude_sonnet",
        json.dumps(_assessment(score=5, decision="MAYBE", reasoning="borderline")),
    )
    review = FakeProvider("codex_gpt55_high", "null")

    result = score_input(
        parsed_input={"title": "T", "description": "D"},
        system_prompt="SYSTEM",
        config={},
        root=tmp_path,
        base_provider=base,
        review_provider=review,
    )

    assert result["fit_score"] == 5
    assert result["decision"] == "MAYBE"
    assert result["reasoning"] == "borderline"
    assert result.get("review_provider") is None
    assert "Invalid review response" in result["review_error"]

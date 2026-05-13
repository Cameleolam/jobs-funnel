import json

import pytest

from scripts.llm.types import ProviderError, ProviderRequest, ProviderResponse
from scripts.scoring import (
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

    def generate(self, request):
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

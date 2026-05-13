import json
from pathlib import Path

from scripts.llm.types import ProviderError, ProviderRequest, ProviderResponse


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
    provider_key = "claude_sonnet"
    model = "claude_sonnet-model"

    def __init__(self):
        self.requests = []

    def generate(self, request: ProviderRequest):
        self.requests.append(request)
        raise ProviderError(self.provider_key, "review failed")


def assessment(score, decision="MAYBE"):
    return {
        "fit_score": score,
        "decision": decision,
        "cv_variant": "software",
        "hard_blockers": [],
        "soft_gaps": [],
        "strong_matches": ["Python"],
        "reasoning": "base reasoning",
        "priority_notes": None,
        "confidence": "medium",
    }


def test_initial_state_marks_missing_calibration_uncalibrated():
    from scripts.graph.state import initial_state

    state = initial_state({"title": "T", "_embedding_calibration_present": False})

    assert state["job"]["title"] == "T"
    assert state["similar_decisions"] == []
    assert state["relevant_cv_bullets"] == []
    assert state["critique_count"] == 0
    assert state["needs_human_review"] is False
    assert state["scored_uncalibrated"] is True


def test_grade_routes_outside_band_to_select_cv():
    from scripts.graph.nodes import grade_route

    state = {"raw_score": 8, "critique_count": 0, "needs_human_review": False}

    assert grade_route(state) == "select_cv"


def test_grade_routes_first_borderline_to_critique():
    from scripts.graph.nodes import grade_route

    state = {"raw_score": 5, "critique_count": 0, "needs_human_review": False}

    assert grade_route(state) == "critique"


def test_grade_routes_decimal_outside_band_without_truncation():
    from scripts.graph.nodes import grade_route

    state = {"raw_score": 6.9, "critique_count": 0, "needs_human_review": False}

    assert grade_route(state) == "select_cv"


def test_grade_routes_second_borderline_to_human():
    from scripts.graph.nodes import grade_route

    state = {"raw_score": 5, "critique_count": 1, "needs_human_review": False}

    assert grade_route(state) == "flag_human"


def test_retrieve_cv_context_node_is_stub():
    from scripts.graph.nodes import retrieve_cv_context_node

    state = {"relevant_cv_bullets": [{"old": "value"}]}

    assert retrieve_cv_context_node(state)["relevant_cv_bullets"] == []


def test_score_node_uses_base_provider_and_records_metadata():
    from scripts.graph.nodes import score_node
    from scripts.graph.state import initial_state

    base = FakeProvider("codex_gpt55_high", json.dumps(assessment(8, "PASS")))
    state = initial_state({"title": "Backend Engineer", "description": "Python APIs"})
    state["system_prompt"] = "SYSTEM"
    state["root"] = Path.cwd()
    state["config"] = {}
    state["base_provider"] = base

    out = score_node(state)

    assert out["raw_score"] == 8
    assert out["assessment"]["scoring_provider"] == "codex_gpt55_high"
    assert out["assessment"]["scoring_model"] == "codex_gpt55_high-model"
    assert "Backend Engineer" in base.requests[0].user_prompt


def test_score_node_routes_list_assessment_to_human_review():
    from scripts.graph.nodes import score_node
    from scripts.graph.state import initial_state

    base = FakeProvider("codex_gpt55_high", json.dumps([assessment(9, "PASS")]))
    state = initial_state({"title": "Backend Engineer", "description": "Python APIs"})
    state["system_prompt"] = "SYSTEM"
    state["root"] = Path.cwd()
    state["config"] = {}
    state["base_provider"] = base

    out = score_node(state)

    assert out["assessment"]["decision"] == "pending_review"
    assert out["assessment"]["needs_human_review"] is True
    assert out["assessment"]["hard_blockers"] == [
        "Scoring provider returned non-object assessment"
    ]


def test_self_critique_uses_review_provider_once_and_preserves_base_metadata():
    from scripts.graph.nodes import score_node, self_critique_node
    from scripts.graph.state import initial_state

    base = FakeProvider("codex_gpt55_high", json.dumps(assessment(5, "MAYBE")))
    review = FakeProvider("claude_sonnet", json.dumps(assessment(7, "PASS")))
    state = initial_state({"title": "Backend Engineer", "description": "Python APIs"})
    state["system_prompt"] = "SYSTEM"
    state["root"] = Path.cwd()
    state["config"] = {}
    state["base_provider"] = base
    state["review_provider"] = review

    scored = score_node(state)
    reviewed = self_critique_node(scored)

    assert reviewed["raw_score"] == 7
    assert reviewed["critique_count"] == 1
    assert reviewed["assessment"]["scoring_provider"] == "codex_gpt55_high"
    assert reviewed["assessment"]["scoring_model"] == "codex_gpt55_high-model"
    assert reviewed["assessment"]["review_provider"] == "claude_sonnet"
    assert reviewed["assessment"]["review_model"] == "claude_sonnet-model"
    assert reviewed["assessment"]["base_fit_score"] == 5
    assert reviewed["assessment"]["base_decision"] == "MAYBE"
    assert len(review.requests) == 1


def test_flag_human_sets_pending_review_assessment():
    from scripts.graph.nodes import flag_human_node

    state = {
        "assessment": assessment(5, "MAYBE"),
        "raw_score": 5,
        "critique_count": 1,
        "needs_human_review": False,
    }

    out = flag_human_node(state)

    assert out["needs_human_review"] is True
    assert out["final_decision"] == "pending_review"
    assert out["assessment"]["decision"] == "pending_review"
    assert out["assessment"]["needs_human_review"] is True
    assert out["assessment"]["critique_count"] == 1


def test_persist_node_preserves_assessment_human_review_flag():
    from scripts.graph.nodes import persist_node

    state = {
        "assessment": {
            "decision": "pending_review",
            "needs_human_review": True,
            "reasoning": "r",
            "confidence": "low",
        },
        "needs_human_review": False,
        "critique_count": 0,
        "scored_uncalibrated": False,
    }

    out = persist_node(state)

    assert out["assessment"]["needs_human_review"] is True
    assert out["assessment"]["explanation"] == "r"
    assert out["assessment"]["confidence"] == "low"
    assert out["assessment"]["critique_count"] == 0


def test_run_filter_flow_high_score_finishes_without_review():
    from scripts.graph.build import run_filter_flow

    base = FakeProvider("codex_gpt55_high", json.dumps(assessment(8, "PASS")))
    result = run_filter_flow(
        {"title": "Backend Engineer", "description": "Python APIs"},
        system_prompt="SYSTEM",
        config={},
        root=Path.cwd(),
        base_provider=base,
    )

    assert result["decision"] == "PASS"
    assert result["needs_human_review"] is False
    assert result["critique_count"] == 0
    assert len(base.requests) == 1


def test_run_filter_flow_borderline_without_review_provider_flags_human():
    from scripts.graph.build import run_filter_flow

    base = FakeProvider("codex_gpt55_high", json.dumps(assessment(5, "MAYBE")))
    result = run_filter_flow(
        {"title": "Backend Engineer", "description": "Python APIs"},
        system_prompt="SYSTEM",
        config={},
        root=Path.cwd(),
        base_provider=base,
    )

    assert result["decision"] == "pending_review"
    assert result["needs_human_review"] is True
    assert result["critique_count"] == 0
    assert result["explanation"]


def test_run_filter_flow_can_disable_review_provider_for_batch_cap():
    from scripts.graph.build import run_filter_flow

    base = FakeProvider("codex_gpt55_high", json.dumps(assessment(5, "MAYBE")))
    review = FakeProvider("claude_sonnet", json.dumps(assessment(7, "PASS")))
    result = run_filter_flow(
        {"title": "Backend Engineer", "description": "Python APIs"},
        system_prompt="SYSTEM",
        config={},
        root=Path.cwd(),
        base_provider=base,
        review_provider=review,
        allow_review=False,
    )

    assert result["decision"] == "pending_review"
    assert result["needs_human_review"] is True
    assert result["critique_count"] == 0
    assert review.requests == []


def test_run_filter_flow_borderline_review_then_human_when_still_borderline():
    from scripts.graph.build import run_filter_flow

    base = FakeProvider("codex_gpt55_high", json.dumps(assessment(5, "MAYBE")))
    review = FakeProvider("claude_sonnet", json.dumps(assessment(5, "MAYBE")))
    result = run_filter_flow(
        {"title": "Backend Engineer", "description": "Python APIs"},
        system_prompt="SYSTEM",
        config={},
        root=Path.cwd(),
        base_provider=base,
        review_provider=review,
    )

    assert result["decision"] == "pending_review"
    assert result["critique_count"] == 1
    assert len(review.requests) == 1
    assert result["base_fit_score"] == 5


def test_run_filter_flow_review_provider_failure_keeps_base_assessment():
    from scripts.graph.build import run_filter_flow

    base = FakeProvider("codex_gpt55_high", json.dumps(assessment(5, "MAYBE")))
    review = FailingProvider()
    result = run_filter_flow(
        {"title": "Backend Engineer", "description": "Python APIs"},
        system_prompt="SYSTEM",
        config={},
        root=Path.cwd(),
        base_provider=base,
        review_provider=review,
    )

    assert result["decision"] == "pending_review"
    assert result["needs_human_review"] is True
    assert result["critique_count"] == 1
    assert result["review_error"] == "review failed"
    assert result["scoring_provider"] == "codex_gpt55_high"
    assert result["strong_matches"] == ["Python"]
    assert len(review.requests) == 1


def test_run_filter_flow_parse_failure_flags_human():
    from scripts.graph.build import run_filter_flow

    base = FakeProvider("codex_gpt55_high", "not json")
    result = run_filter_flow(
        {"title": "Backend Engineer", "description": "Python APIs"},
        system_prompt="SYSTEM",
        config={},
        root=Path.cwd(),
        base_provider=base,
    )

    assert result["fit_score"] is None
    assert result["decision"] == "pending_review"
    assert result["needs_human_review"] is True
    assert result["hard_blockers"] == ["Scoring provider returned unreadable assessment"]

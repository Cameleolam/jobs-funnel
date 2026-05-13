import json

from scripts.llm.parsing import (
    coerce_assessment_list,
    extract_result_text,
    fallback_assessment,
    loads_jsonish,
)


def test_extract_result_text_unwraps_claude_dict():
    stdout = json.dumps({"result": "```json\n[{\"fit_score\": 8}]\n```"})

    assert extract_result_text(stdout) == "```json\n[{\"fit_score\": 8}]\n```"


def test_extract_result_text_unwraps_claude_list():
    stdout = json.dumps([{"result": "[{\"fit_score\": 6}]"}])

    assert extract_result_text(stdout) == "[{\"fit_score\": 6}]"


def test_extract_result_text_keeps_codex_plain_json():
    stdout = '[{"fit_score": 7, "decision": "PASS"}]'

    assert extract_result_text(stdout) == stdout


def test_loads_jsonish_accepts_fenced_json_and_single_quoted_property():
    text = """```json
[
  {
    "fit_score": 2,
    "decision": "SKIP",
    'extracted_salary_max': null
  }
]
```"""

    parsed = loads_jsonish(text)

    assert parsed[0]["fit_score"] == 2
    assert parsed[0]["extracted_salary_max"] is None


def test_loads_jsonish_ignores_surrounding_text():
    text = 'Here is the result:\n[{"fit_score": 5, "decision": "MAYBE"}]\nThanks'

    assert loads_jsonish(text) == [{"fit_score": 5, "decision": "MAYBE"}]


def test_coerce_assessment_list_wraps_single_object_for_batch():
    assessment = {"fit_score": 6, "decision": "MAYBE", "cv_variant": "software"}

    result = coerce_assessment_list(assessment, expected_count=2)

    assert len(result) == 2
    assert result[0]["fit_score"] == 6
    assert result[1]["error_code"] == "BATCH_PADDING"


def test_fallback_assessment_has_parse_update_compatible_shape():
    result = fallback_assessment(
        blocker="Scoring provider response parse error",
        reasoning="Parse error: bad output",
        error_code="PARSE_FAIL",
    )

    assert result == {
        "fit_score": 0,
        "decision": "SKIP",
        "cv_variant": "default",
        "hard_blockers": ["Scoring provider response parse error"],
        "soft_gaps": [],
        "strong_matches": [],
        "reasoning": "Parse error: bad output",
        "priority_notes": None,
        "error_code": "PARSE_FAIL",
    }

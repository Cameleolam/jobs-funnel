"""Tests for Phase 3 calibration retrieval."""
from unittest.mock import MagicMock

import scripts.retrieval as retrieval


def test_format_anchor_prefers_user_note_and_marks_interview():
    anchor = {
        "id": 7,
        "title": "Backend Engineer",
        "company": "Acme",
        "fit_score": 82,
        "calibration_label": "applied",
        "notes": "Interview invite after focused backend pitch.",
        "reasoning": "Claude fallback should not be used.",
        "reached_interview": True,
        "received_offer": False,
    }

    text = retrieval.format_anchor(anchor, index=1)

    assert '1. "Backend Engineer @ Acme"' in text
    assert "Score: 82 -> applied -> reached interview" in text
    assert "Your note: Interview invite after focused backend pitch." in text
    assert "Claude fallback" not in text


def test_format_anchor_falls_back_to_reasoning_and_caps_text():
    anchor = {
        "id": 8,
        "title": "Senior Data Engineer",
        "company": "BigCorp",
        "fit_score": 55,
        "calibration_label": "dismissed",
        "notes": "",
        "reasoning": "x" * 260,
        "reached_interview": False,
        "received_offer": False,
    }

    text = retrieval.format_anchor(anchor, index=2)

    assert '2. "Senior Data Engineer @ BigCorp"' in text
    assert "Score: 55 -> dismissed" in text
    assert "Your prior reasoning: " in text
    assert ("x" * 220) not in text


def test_format_calibration_block_returns_empty_for_no_anchors():
    assert retrieval.format_calibration_block([]) == ""


def test_format_calibration_block_includes_header_and_numbered_anchors():
    anchors = [
        {"id": 1, "title": "A", "company": "C", "fit_score": 90, "calibration_label": "offer", "notes": "great", "reasoning": "", "reached_interview": True, "received_offer": True},
        {"id": 2, "title": "B", "company": "D", "fit_score": 20, "calibration_label": "dismissed", "notes": "", "reasoning": "weak", "reached_interview": False, "received_offer": False},
    ]

    block = retrieval.format_calibration_block(anchors)

    assert block.startswith("CALIBRATION - here's how you handled similar jobs in the past.")
    assert '1. "A @ C"' in block
    assert '2. "B @ D"' in block
    assert "received offer" in block


def test_merge_batch_anchors_dedupes_and_caps_by_weighted_score(monkeypatch):
    monkeypatch.setattr(retrieval, "calibration_k_batch", lambda: 2)
    anchors = [
        [{"id": 1, "weighted_score": 0.2}, {"id": 2, "weighted_score": 0.9}],
        [{"id": 1, "weighted_score": 0.8}, {"id": 3, "weighted_score": 0.7}],
    ]

    merged = retrieval.merge_batch_anchors(anchors)

    assert [a["id"] for a in merged] == [2, 1]
    assert merged[1]["weighted_score"] == 0.8

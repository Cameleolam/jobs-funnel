"""Tests for scripts/dedup.py."""
import scripts.dedup as dedup


def test_classify_similarity_routes_certain_duplicate():
    assert dedup.classify_similarity(0.95) == "vector_certain"
    assert dedup.classify_similarity(0.99) == "vector_certain"


def test_classify_similarity_routes_clear_non_duplicate():
    assert dedup.classify_similarity(0.10) == "vector_clear"
    assert dedup.classify_similarity(0.849) == "vector_clear"


def test_classify_similarity_routes_review_band():
    assert dedup.classify_similarity(0.85) == "claude_review"
    assert dedup.classify_similarity(0.949) == "claude_review"


def test_classify_similarity_rejects_missing_similarity():
    assert dedup.classify_similarity(None) == "no_match"

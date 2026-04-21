"""Shared soft-tag detection: staffing agency, geo mismatch, likely English.

Used by scripts/backfill_tags.py and exercised by tests/scripts/test_soft_tags.py.
The n8n JS crawlers duplicate these rules inline (see scripts/n8n/lib/soft-tags.js)
and must be kept in sync with this module.
"""
from __future__ import annotations


ENGLISH_STOPWORDS = (
    "the", "and", "you", "we", "team", "experience", "requirements",
    "about", "our", "will", "work", "join", "role", "position",
)


def detect_staffing_agency(company: str, patterns: list[str]) -> bool:
    if not company:
        return False
    lower = company.lower()
    return any(p.lower() in lower for p in patterns)


def detect_geo_mismatch(location: str, remote: bool, allowlist: list[str]) -> bool:
    if remote:
        return False
    if not location:
        return True
    lower = location.lower()
    return not any(a.lower() in lower for a in allowlist)


def is_likely_english(description: str) -> bool:
    if not description:
        return False
    sample = description[:500].lower()
    hits = sum(1 for w in ENGLISH_STOPWORDS if w in sample)
    return hits >= 3

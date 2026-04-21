"""Shared soft-tag detection backed by a country pack.

Used by scripts/backfill_tags.py and exercised by tests/scripts/test_soft_tags.py.
The n8n JS crawlers re-implement these rules inline and load the same country
pack JSON files at runtime: keep the rules aligned.
"""
from __future__ import annotations

from scripts.lib.country_pack import CountryPack


def detect_staffing_agency(company: str, pack: CountryPack) -> bool:
    if not company:
        return False
    lower = company.lower()
    return any(p.lower() in lower for p in pack.staffing_patterns)


def detect_geo_mismatch(location: str, remote: bool, pack: CountryPack) -> bool:
    if remote:
        return False
    if not location:
        return True
    lower = location.lower()
    return not any(a.lower() in lower for a in pack.geo_allowlist)


def is_likely_language(description: str, pack: CountryPack, lang: str) -> bool:
    if not description:
        return False
    hint = pack.language_hints.get(lang)
    if hint is None:
        return False
    sample = description[: hint.sample_chars].lower()
    hits = sum(1 for w in hint.stopwords if w in sample)
    return hits >= hint.threshold


def is_likely_english(description: str, pack: CountryPack) -> bool:
    return is_likely_language(description, pack, "en")

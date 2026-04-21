"""Country pack loader: staffing patterns, geo allowlist, language hints.

A country pack lives at countries/<code>/ and contains four JSON files.
Loaded once at runtime by soft_tags.py and backfill_tags.py; the n8n JS
crawlers re-implement the loading inline.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LanguageHint:
    stopwords: tuple[str, ...]
    threshold: int
    sample_chars: int


@dataclass(frozen=True)
class CountryPack:
    code: str
    name: str
    default_language: str
    secondary_languages: tuple[str, ...]
    currency: str
    staffing_patterns: tuple[str, ...]
    geo_allowlist: tuple[str, ...]
    language_hints: dict[str, LanguageHint]


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def load_pack(code: str) -> CountryPack:
    pack_dir = _repo_root() / "countries" / code
    if not pack_dir.is_dir():
        raise FileNotFoundError(f"Country pack '{code}' not found at {pack_dir}")

    country = json.loads((pack_dir / "country.json").read_text(encoding="utf-8"))
    if country["code"] != code:
        raise ValueError(
            f"Code mismatch in {pack_dir}/country.json: expected '{code}', got '{country['code']}'"
        )
    staffing = json.loads((pack_dir / "staffing_patterns.json").read_text(encoding="utf-8"))
    geo = json.loads((pack_dir / "geo_allowlist.json").read_text(encoding="utf-8"))
    lang = json.loads((pack_dir / "language_hints.json").read_text(encoding="utf-8"))

    hints = {
        name: LanguageHint(
            stopwords=tuple(h["stopwords"]),
            threshold=int(h["threshold"]),
            sample_chars=int(h["sample_chars"]),
        )
        for name, h in lang["languages"].items()
    }

    return CountryPack(
        code=country["code"],
        name=country["name"],
        default_language=country["default_language"],
        secondary_languages=tuple(country.get("secondary_languages", [])),
        currency=country["currency"],
        staffing_patterns=tuple(staffing["patterns"]),
        geo_allowlist=tuple(geo["allowlist"]),
        language_hints=hints,
    )

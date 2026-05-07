"""Tests for scripts.lib.country_pack."""
import dataclasses
from pathlib import Path

import pytest

from scripts.lib.country_pack import CountryPack, LanguageHint, load_pack


FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def test_load_de_pack_has_expected_fields():
    pack = load_pack("de")
    assert pack.code == "de"
    assert pack.name == "Germany"
    assert pack.default_language == "de"
    assert "randstad" in pack.staffing_patterns
    assert "germany" in pack.geo_allowlist
    assert "en" in pack.language_hints
    assert pack.language_hints["en"].threshold == 3


def test_load_global_pack_has_empty_allowlist():
    pack = load_pack("global")
    assert pack.code == "global"
    assert pack.geo_allowlist == ()
    assert pack.staffing_patterns == ()


def test_load_pack_missing_raises():
    with pytest.raises(FileNotFoundError) as ei:
        load_pack("zz")
    assert "zz" in str(ei.value)


def test_country_pack_is_immutable_dataclass():
    pack = load_pack("de")
    with pytest.raises(dataclasses.FrozenInstanceError):
        pack.code = "xx"


def test_load_pack_detects_code_mismatch(monkeypatch):
    """Code field in country.json must match directory name."""
    from scripts.lib import country_pack as cp_mod
    monkeypatch.setattr(cp_mod, "_repo_root", lambda: FIXTURES)

    with pytest.raises(ValueError, match="Code mismatch"):
        cp_mod.load_pack("xx")


def test_language_hint_is_frozen():
    pack = load_pack("de")
    hint = pack.language_hints["en"]
    with pytest.raises(dataclasses.FrozenInstanceError):
        hint.threshold = 99

"""Unit tests for the soft-tags detection helpers."""
from scripts.lib.country_pack import load_pack
from scripts.lib.soft_tags import (
    detect_geo_mismatch,
    detect_staffing_agency,
    is_likely_english,
    is_likely_language,
)

PACK_DE = load_pack("de")
PACK_GLOBAL = load_pack("global")


def test_staffing_positive_exact_word():
    assert detect_staffing_agency("Randstad Deutschland GmbH", PACK_DE) is True


def test_staffing_positive_substring():
    assert detect_staffing_agency("Müller Personaldienst GmbH", PACK_DE) is True


def test_staffing_positive_case_insensitive():
    assert detect_staffing_agency("HAYS AG", PACK_DE) is True


def test_staffing_negative():
    assert detect_staffing_agency("Mozilla Corporation", PACK_DE) is False


def test_staffing_empty_company():
    assert detect_staffing_agency("", PACK_DE) is False


def test_staffing_global_pack_never_matches():
    """Empty patterns array means no staffing detection."""
    assert detect_staffing_agency("Randstad Deutschland GmbH", PACK_GLOBAL) is False


def test_geo_mismatch_remote_short_circuits_to_false():
    assert detect_geo_mismatch("São Paulo", True, PACK_DE) is False


def test_geo_mismatch_dach_city_ok():
    assert detect_geo_mismatch("Munich, Germany", False, PACK_DE) is False


def test_geo_mismatch_other_country_mismatch():
    assert detect_geo_mismatch("San Francisco, CA", False, PACK_DE) is True


def test_geo_mismatch_empty_location_with_not_remote_is_mismatch():
    assert detect_geo_mismatch("", False, PACK_DE) is True


def test_geo_mismatch_global_pack_flags_every_nonremote():
    """Empty allowlist means every on-site job is a mismatch."""
    assert detect_geo_mismatch("Berlin", False, PACK_GLOBAL) is True
    assert detect_geo_mismatch("Berlin", True, PACK_GLOBAL) is False


def test_english_hits_threshold():
    desc = "We are hiring. You will work with our team. About the role: requirements are ..."
    assert is_likely_english(desc, PACK_DE) is True


def test_english_german_returns_false():
    desc = "Wir suchen einen Entwickler für unser Team in München. Bewirb dich jetzt."
    assert is_likely_english(desc, PACK_DE) is False


def test_english_empty_returns_false():
    assert is_likely_english("", PACK_DE) is False


def test_is_likely_language_en_matches_english_text():
    desc = "We are looking for a team member with experience in the requirements analysis."
    assert is_likely_language(desc, PACK_DE, "en") is True


def test_is_likely_language_en_rejects_german_text():
    desc = "Wir suchen einen Mitarbeiter mit Erfahrung in der Anforderungsanalyse für unser Team."
    assert is_likely_language(desc, PACK_DE, "en") is False


def test_is_likely_language_de_matches_german_text():
    desc = "Wir sind ein Team und suchen unsere neuen Mitarbeiter für das Projekt."
    assert is_likely_language(desc, PACK_DE, "de") is True


def test_is_likely_language_missing_lang_returns_false():
    """Global pack has no 'de' hint."""
    assert is_likely_language("Wir suchen", PACK_GLOBAL, "de") is False

"""Unit tests for the soft-tags detection helpers."""
from scripts.lib.soft_tags import (
    detect_geo_mismatch,
    detect_staffing_agency,
    is_likely_english,
)

PATTERNS = [
    "zeitarbeit", "personal", "personaldienst", "randstad", "hays",
    "adecco", "manpower", "gi group", "dis ag", "orizon", "tempton",
    "piening", "actief", "robert half",
]

ALLOWLIST = [
    "germany", "deutschland", "munich", "münchen", "berlin", "hamburg",
    "frankfurt", "stuttgart", "köln", "austria", "switzerland",
    "remote", "europe", "eu", "dach", "emea",
]


def test_staffing_positive_exact_word():
    assert detect_staffing_agency("Randstad Deutschland GmbH", PATTERNS) is True


def test_staffing_positive_substring():
    assert detect_staffing_agency("Müller Personaldienst GmbH", PATTERNS) is True


def test_staffing_positive_case_insensitive():
    assert detect_staffing_agency("HAYS AG", PATTERNS) is True


def test_staffing_negative():
    assert detect_staffing_agency("Mozilla Corporation", PATTERNS) is False


def test_staffing_empty_company():
    assert detect_staffing_agency("", PATTERNS) is False


def test_geo_mismatch_remote_short_circuits_to_false():
    assert detect_geo_mismatch("São Paulo", True, ALLOWLIST) is False


def test_geo_mismatch_dach_city_ok():
    assert detect_geo_mismatch("Munich, Germany", False, ALLOWLIST) is False


def test_geo_mismatch_other_country_mismatch():
    assert detect_geo_mismatch("San Francisco, CA", False, ALLOWLIST) is True


def test_geo_mismatch_empty_location_with_not_remote_is_mismatch():
    assert detect_geo_mismatch("", False, ALLOWLIST) is True


def test_english_hits_threshold():
    desc = "We are hiring. You will work with our team. About the role: requirements are ..."
    assert is_likely_english(desc) is True


def test_english_german_returns_false():
    desc = "Wir suchen einen Entwickler für unser Team in München. Bewirb dich jetzt."
    assert is_likely_english(desc) is False


def test_english_empty_returns_false():
    assert is_likely_english("") is False

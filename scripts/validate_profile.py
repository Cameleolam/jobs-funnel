#!/usr/bin/env python3
"""Validate a jobs_funnel profile directory.

Usage:
    python scripts/validate_profile.py profiles/profile1/
    python scripts/validate_profile.py profiles/profile1/ --strict

Exit codes: 0 = valid (warnings OK), 1 = errors found
"""

import json
import sys
from pathlib import Path

REQUIRED_SEARCH_KEYS = {
    "aa_searches": list,
    "an_title_keywords": list,
    "an_tag_keywords": list,
    "an_location_keywords": list,
    "an_negative_keywords": list,
}


def validate_search_json(profile_dir):
    errors = []
    warnings = []
    path = profile_dir / "search.json"

    if not path.exists():
        return ["search.json not found"], []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"search.json: invalid JSON: {e}"], []

    if not isinstance(data, dict):
        return ["search.json: top-level value must be an object"], []

    # Required array keys
    for key, expected_type in REQUIRED_SEARCH_KEYS.items():
        if key not in data:
            errors.append(f"search.json: missing required key '{key}'")
        elif not isinstance(data[key], expected_type):
            errors.append(f"search.json: '{key}' must be {expected_type.__name__}, got {type(data[key]).__name__}")
        elif len(data[key]) == 0:
            warnings.append(f"search.json: '{key}' is empty")

    # Location: modern aa_locations or legacy aa_location + aa_radius_km
    has_modern = "aa_locations" in data
    has_legacy = "aa_location" in data or "aa_radius_km" in data

    if has_modern:
        locs = data["aa_locations"]
        if not isinstance(locs, list):
            errors.append("search.json: 'aa_locations' must be a list")
        elif len(locs) == 0:
            warnings.append("search.json: 'aa_locations' is empty")
        else:
            for i, loc in enumerate(locs):
                if not isinstance(loc, dict):
                    errors.append(f"search.json: aa_locations[{i}] must be an object")
                    continue
                if "location" not in loc or not isinstance(loc["location"], str):
                    errors.append(f"search.json: aa_locations[{i}] missing 'location' (string)")
                if "radius_km" not in loc or not isinstance(loc["radius_km"], (int, float)):
                    errors.append(f"search.json: aa_locations[{i}] missing 'radius_km' (number)")
    elif has_legacy:
        if "aa_location" not in data or not isinstance(data["aa_location"], str):
            errors.append("search.json: legacy 'aa_location' must be a string")
        if "aa_radius_km" not in data or not isinstance(data["aa_radius_km"], (int, float)):
            errors.append("search.json: legacy 'aa_radius_km' must be a number")
        warnings.append("search.json: using legacy aa_location/aa_radius_km — consider migrating to aa_locations")
    else:
        errors.append("search.json: missing location config (need 'aa_locations' or legacy 'aa_location' + 'aa_radius_km')")

    return errors, warnings


def validate_filter_prompt(profile_dir):
    errors = []
    path = profile_dir / "filter_prompt.md"

    if not path.exists():
        return ["filter_prompt.md not found"], []

    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return ["filter_prompt.md is empty"], []

    return errors, []


def validate_cvs(profile_dir):
    errors = []
    warnings = []
    cvs_dir = profile_dir / "cvs"

    if not cvs_dir.exists():
        return [], ["cvs/ directory not found (optional, needed only for CV generation)"]

    html_files = list(cvs_dir.glob("*.html"))
    if not html_files:
        return ["cvs/ directory exists but has no .html files"], []

    variants = sorted(f.stem for f in html_files)
    print(f"  Found CV variants: {', '.join(variants)}")

    return errors, warnings


def validate_generate_prompt(profile_dir):
    warnings = []
    path = profile_dir / "generate_prompt.md"

    if not path.exists():
        return [], ["generate_prompt.md not found (optional)"]

    content = path.read_text(encoding="utf-8").strip()
    if not content:
        warnings.append("generate_prompt.md is empty (optional)")

    return [], warnings


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("Usage: python scripts/validate_profile.py <profile_dir> [--strict]")
        return 1

    strict = "--strict" in sys.argv
    profile_dir = Path(sys.argv[1]).resolve()

    if not profile_dir.is_dir():
        print(f"ERROR: directory not found: {profile_dir}")
        return 1

    print(f"Validating profile: {profile_dir.name}/\n")

    all_errors = []
    all_warnings = []

    for validator in (validate_search_json, validate_filter_prompt, validate_cvs, validate_generate_prompt):
        errs, warns = validator(profile_dir)
        all_errors.extend(errs)
        all_warnings.extend(warns)

    if strict:
        all_errors.extend(all_warnings)
        all_warnings = []

    if all_errors:
        print("ERRORS:")
        for e in all_errors:
            print(f"  - {e}")
        if all_warnings:
            print()

    if all_warnings:
        print("WARNINGS:")
        for w in all_warnings:
            print(f"  - {w}")

    if all_errors or all_warnings:
        print()

    n_err = len(all_errors)
    n_warn = len(all_warnings)
    status = "FAIL" if n_err else "OK"
    print(f"Result: {status} ({n_err} error{'s' if n_err != 1 else ''}, {n_warn} warning{'s' if n_warn != 1 else ''})")

    return 1 if n_err else 0


if __name__ == "__main__":
    sys.exit(main())

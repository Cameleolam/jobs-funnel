import json
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def write_search(profile_dir: Path, crawlers=None):
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "search.json").write_text(
        json.dumps(
            {
                "country": "de",
                "crawlers": crawlers or ["arbeitnow"],
                "aa_searches": ["Backend Engineer"],
                "aa_locations": [{"location": "Berlin", "radius_km": 100}],
                "an_title_keywords": ["backend"],
                "an_tag_keywords": ["python"],
                "an_location_keywords": ["berlin"],
                "an_negative_keywords": ["intern"],
            }
        ),
        encoding="utf-8",
    )
    (profile_dir / "filter_prompt.md").write_text("Score jobs.", encoding="utf-8")


def run_validate(profile_dir: Path):
    return subprocess.run(
        [sys.executable, "scripts/validate_profile.py", str(profile_dir)],
        cwd=REPO,
        capture_output=True,
        text=True,
    )


def test_validate_profile_warns_when_ats_watchlist_selected_without_file(tmp_path):
    profile_dir = tmp_path / "profile"
    write_search(profile_dir, crawlers=["ats_watchlist"])

    result = run_validate(profile_dir)

    assert result.returncode == 0
    assert "company_watchlist.json not found" in result.stdout
    assert "ats_watchlist is selected" in result.stdout


def test_validate_profile_errors_on_malformed_ats_watchlist_entries(tmp_path):
    profile_dir = tmp_path / "profile"
    write_search(profile_dir, crawlers=["ats_watchlist"])
    (profile_dir / "company_watchlist.json").write_text(
        json.dumps(
            [
                {},
                {"company": "Bad ATS", "provider": "personio", "slug": "bad"},
                {
                    "company": "Bad Enabled",
                    "provider": "greenhouse",
                    "slug": "bad-enabled",
                    "enabled": "yes",
                },
            ]
        ),
        encoding="utf-8",
    )

    result = run_validate(profile_dir)

    assert result.returncode == 1
    assert "company_watchlist.json[0]: missing required key 'company'" in result.stdout
    assert "company_watchlist.json[0]: missing required key 'provider'" in result.stdout
    assert "company_watchlist.json[0]: missing required key 'slug'" in result.stdout
    assert "company_watchlist.json[1]: unknown provider 'personio'" in result.stdout
    assert "company_watchlist.json[2]: 'enabled' must be bool" in result.stdout

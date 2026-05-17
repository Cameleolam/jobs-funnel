from pathlib import Path
import re


BASE = Path("ui/templates/base.html").read_text(encoding="utf-8")
STYLES = Path("ui/static/styles.css").read_text(encoding="utf-8")


def test_base_links_static_stylesheet():
    assert 'href="/static/styles.css"' in BASE


def test_base_nav_has_core_sections():
    expected_links = [
        ("/", "Jobs"),
        ("/?view=review", "Review Queue"),
        ("/tracking", "Tracking"),
        ("/runs", "Runs"),
        ("/calibration", "Calibration"),
        ("/system", "System"),
    ]
    nav = re.search(r'<nav class="top-nav">(.*?)</nav>', BASE, re.DOTALL)

    assert nav is not None
    actual_links = re.findall(r'<a href="([^"]+)">([^<]+)</a>', nav.group(1))
    assert actual_links == expected_links


def test_base_nav_styles_target_rendered_class():
    assert ".top-nav" in STYLES

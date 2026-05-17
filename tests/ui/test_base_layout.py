from pathlib import Path
import re


BASE = Path("ui/templates/base.html").read_text(encoding="utf-8")
STYLES = Path("ui/static/styles.css").read_text(encoding="utf-8")


def test_base_links_static_stylesheet():
    assert 'href="/static/styles.css"' in BASE


def test_base_nav_has_core_sections():
    expected_links = [
        ('href="/"', "Jobs"),
        ('href="/?view=review"', "Review Queue"),
        ('href="/tracking"', "Tracking"),
        ('href="/runs"', "Runs"),
        ('href="/calibration"', "Calibration"),
        ('href="/system"', "System"),
    ]
    nav = re.search(r'<nav class="top-nav">(.*?)</nav>', BASE, re.DOTALL)

    assert nav is not None
    cursor = 0
    for href, label in expected_links:
        link = re.search(rf'<a {re.escape(href)}>{re.escape(label)}</a>', nav.group(1))

        assert link is not None
        assert link.start() >= cursor
        cursor = link.end()


def test_base_nav_styles_target_rendered_class():
    assert ".top-nav" in STYLES

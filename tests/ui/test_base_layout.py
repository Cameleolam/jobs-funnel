from pathlib import Path


BASE = Path("ui/templates/base.html").read_text(encoding="utf-8")
STYLES = Path("ui/static/styles.css").read_text(encoding="utf-8")


def test_base_links_static_stylesheet():
    assert 'href="/static/styles.css"' in BASE


def test_base_nav_has_core_sections():
    for href, label in [
        ('href="/"', "Jobs"),
        ('href="/?view=review"', "Review Queue"),
        ('href="/tracking"', "Tracking"),
        ('href="/runs"', "Runs"),
        ('href="/calibration"', "Calibration"),
        ('href="/system"', "System"),
    ]:
        assert href in BASE
        assert label in BASE


def test_base_nav_styles_target_rendered_class():
    assert ".top-nav" in STYLES

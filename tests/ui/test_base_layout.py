from pathlib import Path
import re

from fastapi.testclient import TestClient

import ui.server as srv


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
    nav = re.search(
        r'<nav class="nav-bar top-nav">\s*<div class="nav-bar-inner">(.*?)</div>\s*</nav>',
        BASE,
        re.DOTALL,
    )

    assert nav is not None
    actual_links = re.findall(r'<a href="([^"]+)">([^<]+)</a>', nav.group(1))
    assert actual_links == expected_links


def test_base_nav_styles_use_existing_classes():
    assert ".nav-bar" in STYLES
    assert ".nav-bar-inner" in STYLES
    assert ".top-nav" not in STYLES


def test_static_stylesheet_is_served():
    response = TestClient(srv.app).get("/static/styles.css")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")

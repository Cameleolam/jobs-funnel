from pathlib import Path
import re

from fastapi.testclient import TestClient
from starlette.requests import Request

from ui.rendering import templates
import ui.server as srv


BASE_PATH = Path("ui/templates/base.html")
STYLES_PATH = Path("ui/static/styles.css")


def _base_source():
    return BASE_PATH.read_text(encoding="utf-8")


def _styles_source():
    return STYLES_PATH.read_text(encoding="utf-8")


def _render_base(path="/", query_string=b""):
    request = Request({
        "type": "http",
        "method": "GET",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": query_string,
        "headers": [],
        "scheme": "http",
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
    })
    return templates.get_template("base.html").render(request=request)


def _nav_links(html):
    nav = re.search(
        r'<nav class="app-nav" aria-label="Primary navigation">(.*?)</nav>',
        html,
        re.DOTALL,
    )
    assert nav is not None
    return re.findall(
        r'<a class="app-nav-link(?: active)?" href="([^"]+)">\s*'
        r'<span class="app-nav-text">([^<]+)</span>\s*</a>',
        nav.group(1),
    )


def _active_labels(html):
    return re.findall(
        r'<a class="app-nav-link active" href="[^"]+">\s*'
        r'<span class="app-nav-text">([^<]+)</span>\s*</a>',
        html,
    )


def test_base_links_static_stylesheet():
    assert 'href="/static/styles.css"' in _base_source()


def test_base_shell_has_sidebar_and_main_regions():
    html = _render_base()

    assert '<div class="app-shell">' in html
    assert '<aside class="app-sidebar" aria-label="Primary">' in html
    assert '<main class="app-main">' in html
    assert '<div class="app-content">' in html


def test_sidebar_nav_has_core_sections():
    assert _nav_links(_render_base()) == [
        ("/", "Jobs"),
        ("/?view=review", "Review Queue"),
        ("/tracking", "Tracking"),
        ("/clusters", "Clusters"),
        ("/runs", "Runs"),
        ("/calibration", "Calibration"),
        ("/system", "System"),
    ]


def test_jobs_nav_is_active_for_home():
    assert _active_labels(_render_base("/")) == ["Jobs"]


def test_jobs_nav_is_active_for_job_paths():
    assert _active_labels(_render_base("/jobs/12")) == ["Jobs"]


def test_review_nav_is_active_for_review_query():
    assert _active_labels(_render_base("/", b"view=review")) == ["Review Queue"]


def test_section_nav_is_active_by_path():
    assert _active_labels(_render_base("/tracking")) == ["Tracking"]
    assert _active_labels(_render_base("/clusters")) == ["Clusters"]
    assert _active_labels(_render_base("/runs")) == ["Runs"]
    assert _active_labels(_render_base("/calibration")) == ["Calibration"]
    assert _active_labels(_render_base("/system")) == ["System"]


def test_review_query_does_not_override_section_paths():
    assert _active_labels(_render_base("/tracking", b"view=review")) == ["Tracking"]


def test_static_stylesheet_is_served():
    response = TestClient(srv.app).get("/static/styles.css")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")


def test_shell_styles_define_responsive_sidebar_layout():
    styles = _styles_source()

    expected_fragments = [
        ":root",
        ".app-shell",
        ".app-sidebar",
        ".app-brand",
        ".app-nav",
        ".app-nav-link.active",
        ".app-main",
        ".app-content",
        "@media (max-width: 900px)",
    ]
    for fragment in expected_fragments:
        assert fragment in styles

    assert ".nav-bar" not in styles
    assert ".nav-bar-inner" not in styles


def test_job_status_stripes_render_on_first_table_cell():
    styles = _styles_source()

    assert ".jobs-table tr.decision-PASS > td:first-child" in styles
    assert ".jobs-table tr.status-review > td:first-child" in styles


def test_filter_checkbox_styles_stay_checkbox_sized():
    styles = _styles_source()

    assert '.filter-bar input:not([type="checkbox"]):not([type="hidden"])' in styles
    assert '.filter-secondary input[type="checkbox"]' in styles

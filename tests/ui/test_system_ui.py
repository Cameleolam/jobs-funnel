import inspect

from fastapi.testclient import TestClient

from scripts import doctor
from ui.config import STATIC_DIR, TEMPLATES_DIR
from ui.routes import system
from ui.services import system_health
import ui.server as srv


def test_collect_system_health_maps_doctor_checks(monkeypatch):
    monkeypatch.setattr(
        system_health.doctor,
        "collect_checks",
        lambda: [
            doctor.CheckResult("Postgres", "ok", "Postgres reachable"),
            doctor.CheckResult("n8n", "fail", "n8n is not reachable", "Start n8n."),
        ],
    )

    assert system_health.collect_system_health() == [
        {"name": "Postgres", "status": "ok", "message": "Postgres reachable", "action": ""},
        {"name": "n8n", "status": "fail", "message": "n8n is not reachable", "action": "Start n8n."},
    ]


def test_system_page_renders_health_checks(monkeypatch):
    monkeypatch.setattr(
        system.system_health,
        "collect_system_health",
        lambda: [
            {"name": "Postgres", "status": "ok", "message": "Postgres reachable", "action": ""},
            {"name": "n8n", "status": "fail", "message": "n8n is not reachable", "action": "Start n8n with: n8n start"},
        ],
    )

    response = TestClient(srv.app).get("/system")

    assert response.status_code == 200
    assert "System" in response.text
    assert "Postgres reachable" in response.text
    assert "Start n8n with: n8n start" in response.text
    assert "status-fail" in response.text


def test_system_page_route_uses_sync_endpoint():
    assert not inspect.iscoroutinefunction(system.system_page)


def test_nav_exposes_system_page():
    html = (TEMPLATES_DIR / "base.html").read_text(encoding="utf-8")

    assert 'href="/system"' in html


def test_base_template_has_system_health_styles():
    styles = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")

    assert ".health-row" in styles
    assert ".badge-ok" in styles
    assert ".badge-warn" in styles
    assert ".badge-fail" in styles

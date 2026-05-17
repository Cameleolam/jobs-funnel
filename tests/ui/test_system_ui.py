from fastapi.testclient import TestClient

import ui.server as srv


def test_system_page_renders_health_checks(monkeypatch):
    monkeypatch.setattr(
        srv.system_health,
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


def test_nav_exposes_system_page():
    html = (srv.TEMPLATES_DIR / "base.html").read_text(encoding="utf-8")

    assert 'href="/system"' in html

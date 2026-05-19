from fastapi.testclient import TestClient

from ui.routes import tracking
from ui.server import app


EXPECTED_ROUTES = {
    ("/", "GET"),
    ("/jobs", "GET"),
    ("/export", "GET"),
    ("/jobs/new", "GET"),
    ("/jobs/new", "POST"),
    ("/jobs/{job_id}", "GET"),
    ("/jobs/{job_id}", "PATCH"),
    ("/jobs/{job_id}/status", "PATCH"),
    ("/jobs/{job_id}/notes", "PATCH"),
    ("/jobs/{job_id}/review", "PATCH"),
    ("/jobs/{job_id}/rescore", "POST"),
    ("/jobs/{job_id}/retry", "POST"),
    ("/jobs/{job_id}/duplicate", "PATCH"),
    ("/jobs/{job_id}/track", "POST"),
    ("/stats", "GET"),
    ("/runs", "GET"),
    ("/runs/list", "GET"),
    ("/calibration", "GET"),
    ("/calibration/proposals", "POST"),
    ("/calibration/proposals/{proposal_id}/apply", "POST"),
    ("/calibration/proposals/{proposal_id}/rollback", "POST"),
    ("/system", "GET"),
    ("/tracking", "GET"),
    ("/api/tracking/jobs", "GET"),
    ("/api/tracking/jobs/{job_id}/start", "POST"),
    ("/api/tracking/jobs/{job_id}/stop", "POST"),
    ("/api/tracking/jobs/{job_id}/close", "POST"),
    ("/api/tracking/jobs/{job_id}/reopen", "POST"),
    ("/api/tracking/events", "POST"),
    ("/api/tracking/events/{event_id}", "DELETE"),
    ("/api/tracking/events/{event_id}", "PATCH"),
}

TRACKING_ROUTES = {
    ("/tracking", "GET"),
    ("/api/tracking/jobs", "GET"),
    ("/api/tracking/jobs/{job_id}/start", "POST"),
    ("/api/tracking/jobs/{job_id}/stop", "POST"),
    ("/api/tracking/jobs/{job_id}/close", "POST"),
    ("/api/tracking/jobs/{job_id}/reopen", "POST"),
    ("/api/tracking/events", "POST"),
    ("/api/tracking/events/{event_id}", "DELETE"),
    ("/api/tracking/events/{event_id}", "PATCH"),
}


def test_expected_routes_are_registered():
    registered_routes = {
        (route.path, method)
        for route in app.routes
        for method in getattr(route, "methods", set())
    }

    assert EXPECTED_ROUTES <= registered_routes


def test_tracking_routes_are_registered_on_tracking_router():
    registered_routes = {
        (route.path, method)
        for route in tracking.router.routes
        for method in getattr(route, "methods", set())
    }

    assert TRACKING_ROUTES <= registered_routes


def test_static_css_is_served():
    response = TestClient(app).get("/static/styles.css")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")

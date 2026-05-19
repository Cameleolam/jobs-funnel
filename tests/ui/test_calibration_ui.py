from fastapi.testclient import TestClient

from ui.config import TEMPLATES_DIR
from ui.rendering import templates
from ui.routes import calibration
import ui.server as srv


def _active_settings(**overrides):
    values = {
        "review_low": 4,
        "review_high": 6,
        "calibration_k": 3,
        "calibration_k_batch": 6,
        "calibration_min_pool": 3,
        "weight_offer": 1.5,
        "weight_interview": 1.4,
        "weight_applied": 1.2,
        "weight_dismiss_note": 1.2,
        "weight_dismiss": 0.8,
        "weight_interested": 0.7,
        "source": "env",
        "active_proposal_id": None,
    }
    values.update(overrides)
    return values


def test_calibration_page_renders_active_settings(monkeypatch):
    monkeypatch.setattr(
        calibration.calibration_settings,
        "load_active_settings",
        lambda force=False: _active_settings(),
    )
    monkeypatch.setattr(calibration.calibration_proposals, "list_proposals", lambda limit=20: [])

    response = TestClient(srv.app).get("/calibration")

    assert response.status_code == 200
    assert "Calibration" in response.text
    assert "Review band" in response.text
    assert "4-6" in response.text
    assert "Generate proposal" in response.text
    assert 'id="calibration-content"' in response.text
    assert 'hx-target="#calibration-content"' in response.text


def test_generate_proposal_endpoint_renders_proposal_partial(monkeypatch):
    monkeypatch.setattr(
        calibration.calibration_settings,
        "load_active_settings",
        lambda force=False: _active_settings(),
    )
    monkeypatch.setattr(
        calibration.calibration_proposals,
        "generate_proposal",
        lambda window_days=90: {"id": 3, "status": "proposed"},
    )
    monkeypatch.setattr(
        calibration.calibration_proposals,
        "list_proposals",
        lambda limit=20: [
            {
                "id": 3,
                "status": "proposed",
                "confidence": "low",
                "sample_counts": {"jobs": 10},
                "proposed_settings": {},
                "rationale": {},
            }
        ],
    )

    response = TestClient(srv.app).post(
        "/calibration/proposals",
        data={"window_days": "90"},
    )

    assert response.status_code == 200
    assert "Active Settings" in response.text
    assert "proposal-3" in response.text
    assert "Apply" in response.text


def test_apply_and_rollback_endpoints_call_service(monkeypatch):
    calls = []
    monkeypatch.setattr(
        calibration.calibration_settings,
        "load_active_settings",
        lambda force=False: _active_settings(),
    )
    monkeypatch.setattr(
        calibration.calibration_proposals,
        "apply_proposal",
        lambda proposal_id: calls.append(("apply", proposal_id)) or {},
    )
    monkeypatch.setattr(
        calibration.calibration_proposals,
        "rollback_proposal",
        lambda proposal_id: calls.append(("rollback", proposal_id)) or {},
    )
    monkeypatch.setattr(calibration.calibration_proposals, "list_proposals", lambda limit=20: [])

    client = TestClient(srv.app)
    apply_response = client.post("/calibration/proposals/7/apply")
    rollback_response = client.post("/calibration/proposals/7/rollback")

    assert apply_response.status_code == 200
    assert rollback_response.status_code == 200
    assert calls == [("apply", 7), ("rollback", 7)]


def test_apply_endpoint_response_includes_refreshed_active_settings(monkeypatch):
    monkeypatch.setattr(
        calibration.calibration_settings,
        "load_active_settings",
        lambda force=False: _active_settings(
            review_low=2,
            review_high=8,
            source="proposal",
            active_proposal_id=7,
        ),
    )
    monkeypatch.setattr(calibration.calibration_proposals, "apply_proposal", lambda proposal_id: {})
    monkeypatch.setattr(
        calibration.calibration_proposals,
        "list_proposals",
        lambda limit=20: [
            {
                "id": 7,
                "status": "applied",
                "confidence": "high",
                "sample_counts": {},
                "proposed_settings": {"review_low": 2, "review_high": 8},
                "rationale": {},
                "previous_settings": _active_settings(),
            }
        ],
    )

    response = TestClient(srv.app).post("/calibration/proposals/7/apply")

    assert response.status_code == 200
    assert "Active Settings" in response.text
    assert "2-8" in response.text
    assert "proposal" in response.text
    assert "<strong>7</strong>" in response.text


def test_rollback_endpoint_response_includes_refreshed_active_settings(monkeypatch):
    monkeypatch.setattr(
        calibration.calibration_settings,
        "load_active_settings",
        lambda force=False: _active_settings(active_proposal_id=None),
    )
    monkeypatch.setattr(calibration.calibration_proposals, "rollback_proposal", lambda proposal_id: {})
    monkeypatch.setattr(
        calibration.calibration_proposals,
        "list_proposals",
        lambda limit=20: [
            {
                "id": 7,
                "status": "rolled_back",
                "confidence": "high",
                "sample_counts": {},
                "proposed_settings": {"review_low": 2, "review_high": 8},
                "rationale": {},
                "previous_settings": _active_settings(),
            }
        ],
    )

    response = TestClient(srv.app).post("/calibration/proposals/7/rollback")

    assert response.status_code == 200
    assert "Active Settings" in response.text
    assert "4-6" in response.text
    assert "<strong>-</strong>" in response.text


def test_generate_proposal_state_error_returns_visible_error(monkeypatch):
    def fail_generate(window_days=90):
        raise calibration.calibration_proposals.ProposalStateError("window_days must be positive")

    monkeypatch.setattr(
        calibration.calibration_settings,
        "load_active_settings",
        lambda force=False: _active_settings(),
    )
    monkeypatch.setattr(calibration.calibration_proposals, "generate_proposal", fail_generate)
    monkeypatch.setattr(calibration.calibration_proposals, "list_proposals", lambda limit=20: [])

    response = TestClient(srv.app, raise_server_exceptions=False).post(
        "/calibration/proposals",
        data={"window_days": "90"},
    )

    assert response.status_code == 200
    assert "calibration-error" in response.text
    assert "window_days must be positive" in response.text
    assert "Active Settings" in response.text


def test_apply_proposal_state_error_returns_visible_error(monkeypatch):
    def fail_apply(proposal_id):
        raise calibration.calibration_proposals.ProposalStateError(
            f"Proposal {proposal_id} is not proposed"
        )

    monkeypatch.setattr(
        calibration.calibration_settings,
        "load_active_settings",
        lambda force=False: _active_settings(),
    )
    monkeypatch.setattr(calibration.calibration_proposals, "apply_proposal", fail_apply)
    monkeypatch.setattr(calibration.calibration_proposals, "list_proposals", lambda limit=20: [])

    response = TestClient(srv.app).post("/calibration/proposals/7/apply")

    assert response.status_code == 200
    assert "calibration-error" in response.text
    assert "Proposal 7 is not proposed" in response.text
    assert "Active Settings" in response.text


def test_rollback_proposal_state_error_returns_visible_error(monkeypatch):
    def fail_rollback(proposal_id):
        raise calibration.calibration_proposals.ProposalStateError(
            f"Proposal {proposal_id} is not applied"
        )

    monkeypatch.setattr(
        calibration.calibration_settings,
        "load_active_settings",
        lambda force=False: _active_settings(),
    )
    monkeypatch.setattr(calibration.calibration_proposals, "rollback_proposal", fail_rollback)
    monkeypatch.setattr(calibration.calibration_proposals, "list_proposals", lambda limit=20: [])

    response = TestClient(srv.app).post("/calibration/proposals/7/rollback")

    assert response.status_code == 200
    assert "calibration-error" in response.text
    assert "Proposal 7 is not applied" in response.text
    assert "Active Settings" in response.text


def test_rollback_button_only_renders_for_active_applied_proposal():
    html = templates.get_template("partials/calibration_proposals.html").render(
        request={},
        active=_active_settings(active_proposal_id=2),
        proposals=[
            {
                "id": 1,
                "status": "applied",
                "confidence": "high",
                "sample_counts": {},
                "proposed_settings": {},
                "rationale": {},
                "previous_settings": _active_settings(),
            },
            {
                "id": 2,
                "status": "applied",
                "confidence": "high",
                "sample_counts": {},
                "proposed_settings": {},
                "rationale": {},
                "previous_settings": _active_settings(),
            },
        ],
    )

    assert 'hx-post="/calibration/proposals/1/rollback"' not in html
    assert 'hx-post="/calibration/proposals/2/rollback"' in html


def test_proposals_template_renders_compact_analytics_summary():
    html = templates.get_template("partials/calibration_proposals.html").render(
        request={},
        active=_active_settings(),
        proposals=[
            {
                "id": 9,
                "status": "proposed",
                "confidence": "medium",
                "sample_counts": {
                    "jobs": 40,
                    "review_decisions": 12,
                    "downstream_outcomes": 8,
                },
                "metrics": {
                    "score_bands": {
                        "below_review": {"total": 6, "pursued": 2, "dismissed": 1},
                        "review_band": {"total": 20, "pursued": 5, "dismissed": 4},
                        "above_review": {"total": 14, "pursued": 9, "dismissed": 3},
                    },
                    "proposal": {
                        "guards": {
                            "projected_review_jobs": 22,
                            "projected_review_cap": 25.0,
                        },
                        "evidence": {"false_positives": 3, "false_negatives": 2},
                    },
                },
                "proposed_settings": {"review_low": 3, "review_high": 7},
                "rationale": {"review_band": "expanded", "weights": "adjusted"},
            }
        ],
    )

    assert "below 6 / pursued 2 / dismissed 1" in html
    assert "review 20 / pursued 5 / dismissed 4" in html
    assert "above 14 / pursued 9 / dismissed 3" in html
    assert "false positives 3" in html
    assert "false negatives 2" in html
    assert "projected review 22 / cap 25.0" in html


def test_calibration_proposals_render_human_summary():
    html = templates.get_template("partials/calibration_proposals.html").render(
        request={},
        active=_active_settings(),
        proposals=[
            {
                "id": 12,
                "status": "proposed",
                "confidence": "medium",
                "sample_counts": {"jobs": 20},
                "proposed_settings": {"review_low": 3, "review_high": 6},
                "metrics": {},
                "rationale": {},
                "summary_lines": ["You pursued 4 low-scored jobs."],
            }
        ],
    )

    assert "You pursued 4 low-scored jobs." in html


def test_proposals_template_handles_older_rows_without_metrics_summary():
    html = templates.get_template("partials/calibration_proposals.html").render(
        request={},
        active=_active_settings(),
        proposals=[
            {
                "id": 10,
                "status": "proposed",
                "confidence": "low",
                "sample_counts": {"jobs": 5},
                "proposed_settings": {},
                "rationale": {},
            }
        ],
    )

    assert "proposal-10" in html
    assert "Analytics unavailable" in html


def test_nav_exposes_calibration_page():
    html = (TEMPLATES_DIR / "base.html").read_text(encoding="utf-8")

    assert 'href="/calibration"' in html

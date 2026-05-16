from fastapi.testclient import TestClient

import ui.server as srv


def test_calibration_page_renders_active_settings(monkeypatch):
    monkeypatch.setattr(
        srv.calibration_settings,
        "load_active_settings",
        lambda force=False: {
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
        },
    )
    monkeypatch.setattr(srv.calibration_proposals, "list_proposals", lambda limit=20: [])

    response = TestClient(srv.app).get("/calibration")

    assert response.status_code == 200
    assert "Calibration" in response.text
    assert "Review band" in response.text
    assert "4-6" in response.text
    assert "Generate proposal" in response.text


def test_generate_proposal_endpoint_renders_proposal_partial(monkeypatch):
    monkeypatch.setattr(
        srv.calibration_proposals,
        "generate_proposal",
        lambda window_days=90: {"id": 3, "status": "proposed"},
    )
    monkeypatch.setattr(
        srv.calibration_proposals,
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
    assert "proposal-3" in response.text
    assert "Apply" in response.text


def test_apply_and_rollback_endpoints_call_service(monkeypatch):
    calls = []
    monkeypatch.setattr(
        srv.calibration_proposals,
        "apply_proposal",
        lambda proposal_id: calls.append(("apply", proposal_id)) or {},
    )
    monkeypatch.setattr(
        srv.calibration_proposals,
        "rollback_proposal",
        lambda proposal_id: calls.append(("rollback", proposal_id)) or {},
    )
    monkeypatch.setattr(srv.calibration_proposals, "list_proposals", lambda limit=20: [])

    client = TestClient(srv.app)
    apply_response = client.post("/calibration/proposals/7/apply")
    rollback_response = client.post("/calibration/proposals/7/rollback")

    assert apply_response.status_code == 200
    assert rollback_response.status_code == 200
    assert calls == [("apply", 7), ("rollback", 7)]


def test_apply_proposal_state_error_returns_message(monkeypatch):
    def fail_apply(proposal_id):
        raise srv.calibration_proposals.ProposalStateError(
            f"Proposal {proposal_id} is not proposed"
        )

    monkeypatch.setattr(srv.calibration_proposals, "apply_proposal", fail_apply)
    list_proposals = []
    monkeypatch.setattr(
        srv.calibration_proposals,
        "list_proposals",
        lambda limit=20: list_proposals.append(limit) or [],
    )

    response = TestClient(srv.app).post("/calibration/proposals/7/apply")

    assert response.status_code == 400
    assert response.text == "Proposal 7 is not proposed"
    assert list_proposals == []


def test_rollback_proposal_state_error_returns_message(monkeypatch):
    def fail_rollback(proposal_id):
        raise srv.calibration_proposals.ProposalStateError(
            f"Proposal {proposal_id} is not applied"
        )

    monkeypatch.setattr(srv.calibration_proposals, "rollback_proposal", fail_rollback)
    list_proposals = []
    monkeypatch.setattr(
        srv.calibration_proposals,
        "list_proposals",
        lambda limit=20: list_proposals.append(limit) or [],
    )

    response = TestClient(srv.app).post("/calibration/proposals/7/rollback")

    assert response.status_code == 400
    assert response.text == "Proposal 7 is not applied"
    assert list_proposals == []


def test_nav_exposes_calibration_page():
    html = (srv.TEMPLATES_DIR / "base.html").read_text(encoding="utf-8")

    assert 'href="/calibration"' in html

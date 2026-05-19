"""Calibration UI routes."""

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from scripts import calibration_proposals
from scripts import calibration_settings
from ui.rendering import render
from ui.services.calibration_presenter import proposal_summary_lines


router = APIRouter()


def _calibration_context(error: str | None = None):
    active = calibration_settings.load_active_settings(force=True)
    proposals = calibration_proposals.list_proposals(limit=20)
    proposals = [
        {**proposal, "summary_lines": proposal_summary_lines(proposal)}
        for proposal in proposals
    ]
    return {
        "active": active,
        "proposals": proposals,
        "error": error,
    }


def _render_calibration_content(request: Request, error: str | None = None):
    return render(request, "partials/calibration_content.html", _calibration_context(error))


@router.get("/calibration", response_class=HTMLResponse)
async def calibration_page(request: Request):
    return render(request, "calibration.html", _calibration_context())


@router.post("/calibration/proposals", response_class=HTMLResponse)
async def calibration_generate_proposal(
    request: Request,
    window_days: int = Form(90),
):
    try:
        calibration_proposals.generate_proposal(window_days=window_days)
    except calibration_proposals.ProposalStateError as exc:
        return _render_calibration_content(request, str(exc))
    return _render_calibration_content(request)


@router.post("/calibration/proposals/{proposal_id}/apply", response_class=HTMLResponse)
async def calibration_apply_proposal(request: Request, proposal_id: int):
    try:
        calibration_proposals.apply_proposal(proposal_id)
    except calibration_proposals.ProposalStateError as exc:
        return _render_calibration_content(request, str(exc))
    return _render_calibration_content(request)


@router.post("/calibration/proposals/{proposal_id}/rollback", response_class=HTMLResponse)
async def calibration_rollback_proposal(request: Request, proposal_id: int):
    try:
        calibration_proposals.rollback_proposal(proposal_id)
    except calibration_proposals.ProposalStateError as exc:
        return _render_calibration_content(request, str(exc))
    return _render_calibration_content(request)

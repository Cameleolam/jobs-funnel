"""System health UI routes."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ui.rendering import render
from ui.services import system_health


router = APIRouter()


@router.get("/system", response_class=HTMLResponse)
def system_page(request: Request):
    return render(request, "system.html", {"checks": system_health.collect_system_health()})

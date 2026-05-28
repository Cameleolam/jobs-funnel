"""Local semantic cluster explorer routes."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ui.rendering import render
from ui.services import cluster_graph


router = APIRouter()


@router.get("/clusters", response_class=HTMLResponse)
async def clusters_page(request: Request):
    return render(request, "clusters.html")


@router.get("/api/clusters/graph")
async def api_clusters_graph(
    days: str = "30",
    limit: str = "250",
    threshold: str = "0.82",
    color_by: str = "decision",
    company_cap: str = "25",
    hide_same_company_edges: str = "true",
):
    return cluster_graph.get_cluster_graph(
        days=days,
        limit=limit,
        threshold=threshold,
        color_by=color_by,
        company_cap=company_cap,
        hide_same_company_edges=hide_same_company_edges,
    )

"""Jobs Funnel - lightweight review UI.

Start:
    cd D:/projects/jobs_funnel
    python -m uvicorn ui.server:app --port 8080 --reload
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from ui.config import STATIC_DIR
from ui.routes import calibration, clusters, jobs, runs, system, tracking


app = FastAPI(title="Jobs Funnel UI")
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(jobs.router)
app.include_router(runs.router)
app.include_router(calibration.router)
app.include_router(clusters.router)
app.include_router(system.router)
app.include_router(tracking.router)

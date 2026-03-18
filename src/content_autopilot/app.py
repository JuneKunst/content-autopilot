from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from content_autopilot.dashboard.api import router as dashboard_router

app = FastAPI(
    title="Content Autopilot",
    description="Automated content collection, processing, and publishing platform",
    version="0.1.0",
)

# CORS — allow browser access from any origin (dashboard is password-protected)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files if directory exists
_static_dir = os.path.join(os.path.dirname(__file__), "dashboard", "static")
if os.path.exists(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

# Include dashboard API router
app.include_router(dashboard_router)


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(url="/api/dashboard/overview")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}

"""
FastAPI application entry point for LPDG Gateway Prioritization.
"""

from __future__ import annotations

import pathlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.dependencies import get_settings
from api.routers import drift, pipeline, predictions, registry, rollback

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "MLOps-grade API for Gateway Visit Prioritization, "
        "Model Registry, Drift Monitoring, and Rollback."
    ),
)

# CORS: intentionally open for evaluation/demo. In production this would be
# restricted to the dashboard origin only. See DECISIONS.md ADR 0006.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routers
app.include_router(registry.router)
app.include_router(predictions.router)
app.include_router(rollback.router)
app.include_router(drift.router)
app.include_router(pipeline.router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "version": settings.app_version}


# Mount frontend static distribution if built
frontend_dist = pathlib.Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")

"""
API endpoints for Drift Monitoring.
"""

from __future__ import annotations

import contextlib
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import Settings, get_settings
from src.drift_monitor import count_consecutive_flags, run_drift_check

router = APIRouter(prefix="/api/drift", tags=["Drift"])


@router.get("/status")
def get_drift_status(settings: Settings = Depends(get_settings)) -> dict[str, Any]:  # noqa: B008
    consecutive = count_consecutive_flags(settings.reports_dir)

    # Read latest report if available
    report_files = sorted(settings.reports_dir.glob("*.json"), reverse=True)
    latest_report = None
    if report_files:
        with contextlib.suppress(Exception):
            latest_report = json.loads(report_files[0].read_text(encoding="utf-8"))

    return {
        "consecutive_flagged_weeks": consecutive,
        "retrain_recommended": consecutive >= 3,
        "total_reports": len(report_files),
        "latest_report": latest_report,
    }


@router.get("/history")
def get_drift_history(settings: Settings = Depends(get_settings)) -> dict[str, Any]:  # noqa: B008
    report_files = sorted(settings.reports_dir.glob("*.json"), reverse=True)
    reports = []
    for f in report_files:
        try:
            reports.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            continue
    return {
        "reports": reports,
        "total": len(reports),
    }


@router.post("/run")
def trigger_drift_check(settings: Settings = Depends(get_settings)) -> dict[str, Any]:  # noqa: B008
    if not settings.data_dir.exists():
        raise HTTPException(status_code=404, detail="Data directory not found for drift check")
    try:
        report = run_drift_check(
            data_dir=settings.data_dir,
            reports_dir=settings.reports_dir,
            models_dir=settings.models_dir,
        )
        return {
            "status": "success",
            "report": json.loads(report.to_json()),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Drift check failed: {e}") from e

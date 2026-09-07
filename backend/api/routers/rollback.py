"""
API endpoints for Rollback management and verification.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.dependencies import Settings, get_settings
from src.predict import predict
from src.rollback import (
    get_current_active,
    get_rollback_log,
    rollback_to,
    verify,
)

router = APIRouter(prefix="/api/rollback", tags=["Rollback"])


class RollbackBody(BaseModel):
    to_version: str
    reason: str


@router.get("/log")
def get_log(settings: Settings = Depends(get_settings)) -> dict[str, Any]:  # noqa: B008
    logs = get_rollback_log(settings.models_dir)
    return {
        "total_entries": len(logs),
        "logs": logs,
    }


@router.post("/execute")
def execute_rollback(
    body: RollbackBody,
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> dict[str, Any]:
    try:
        from_version = get_current_active(settings.models_dir) or "none"
        rollback_to(to_version=body.to_version, reason=body.reason, models_dir=settings.models_dir)

        # Regenerate predictions using the newly activated version
        if settings.data_dir.exists():
            predict(
                data_dir=settings.data_dir,
                out_path=settings.predictions_path,
                models_dir=settings.models_dir,
            )

        return {
            "status": "success",
            "from_version": from_version,
            "to_version": body.to_version,
            "reason": body.reason,
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rollback execution failed: {e}") from e


@router.post("/verify")
def verify_version(
    version_id: str | None = None,
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> dict[str, Any]:
    if not settings.data_dir.exists():
        raise HTTPException(status_code=404, detail="Data directory not found for verification")

    active = version_id or get_current_active(settings.models_dir)
    if not active:
        raise HTTPException(status_code=400, detail="No active version to verify")

    try:
        passed = verify(
            data_dir=settings.data_dir, version_id=active, models_dir=settings.models_dir
        )
        return {
            "version_id": active,
            "verified": passed,
            "status": "PASS" if passed else "FAIL",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Verification failed with error: {e}") from e

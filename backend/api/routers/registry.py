"""
API endpoints for Model Registry.
"""

from __future__ import annotations

from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import Settings, get_settings
from src.rollback import list_versions, get_current_active
from src.train import load_model_artifact

router = APIRouter(prefix="/api/registry", tags=["Registry"])


@router.get("")
def get_registry(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    active = get_current_active(settings.models_dir)
    versions = list_versions(settings.models_dir)
    return {
        "active_version": active,
        "total_versions": len(versions),
        "versions": versions,
    }


@router.get("/versions/{version_id}")
def get_version_details(version_id: str, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    try:
        artifact = load_model_artifact(version_id, settings.models_dir)
        artifact["is_active"] = (version_id == get_current_active(settings.models_dir))
        return artifact
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

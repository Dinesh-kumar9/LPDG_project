"""
API endpoints for Gateway Predictions.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from api.dependencies import Settings, get_settings
from src.load import load_gateway_master, normalize_gateway_id
from src.predict import predict

router = APIRouter(prefix="/api/predictions", tags=["Predictions"])


@router.get("")
def get_predictions(
    week_start: str | None = Query(None, description="Filter by Monday date YYYY-MM-DD"),
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> dict[str, Any]:
    pred_path = settings.predictions_path
    if not pred_path.exists():
        # Generate predictions if not already present
        if not settings.data_dir.exists():
            raise HTTPException(
                status_code=404, detail="Data directory not found to generate predictions"
            )
        try:
            predict(data_dir=settings.data_dir, out_path=pred_path, models_dir=settings.models_dir)
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to generate predictions: {e}"
            ) from e

    df = pd.read_csv(pred_path)

    # Optional enrichment with gateway_master data
    try:
        master_df = load_gateway_master(settings.data_dir)
        master_dict = master_df.set_index("gateway_id").to_dict(orient="index")
    except Exception:  # noqa: BLE001
        master_dict = {}

    records = []
    for rec in df.to_dict(orient="records"):
        norm_id = normalize_gateway_id(str(rec.get("gateway_id", "")))
        extra = master_dict.get(norm_id, {})
        records.append(
            {
                "week_start": str(rec.get("week_start", "")),
                "rank": int(rec.get("rank", 0)),
                "gateway_id": norm_id,
                "score": float(rec.get("score", 0.0)),
                "reason": str(rec.get("reason", "")),
                "site_type": extra.get("site_type"),
                "region": extra.get("region"),
                "hw_model": extra.get("hw_model"),
                "n_meters_installed": extra.get("n_meters_installed"),
            }
        )

    if week_start:
        records = [r for r in records if r["week_start"] == week_start]

    weeks = sorted(df["week_start"].unique().tolist())

    return {
        "total_rows": len(records),
        "available_weeks": weeks,
        "selected_week": week_start,
        "predictions": records,
    }


@router.post("/run")
def regenerate_predictions(
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> dict[str, Any]:
    """
    Regenerate predictions.csv from current data and active model version.

    Use this after new telemetry data arrives — drops the cached predictions.csv
    and re-runs the full prediction pipeline from disk. The container does not
    need to be restarted; the next GET /api/predictions will serve fresh results.

    DESIGN (ADR 0006): This endpoint exists as a live-session safety net.
    Training is still CLI-only (POST /api/pipeline/train returns 501). This
    endpoint only re-runs inference against the already-active model version.
    """
    if not settings.data_dir.exists():
        raise HTTPException(status_code=404, detail="Data directory not found")

    # Remove stale file so predict() always generates a fresh output
    pred_path = settings.predictions_path
    if pred_path.exists():
        pred_path.unlink()

    try:
        out_path = predict(
            data_dir=settings.data_dir,
            out_path=pred_path,
            models_dir=settings.models_dir,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Prediction regeneration failed: {e}"
        ) from e

    df = pd.read_csv(out_path)
    return {
        "status": "regenerated",
        "rows": len(df),
        "weeks": sorted(df["week_start"].unique().tolist()),
        "output_path": str(out_path),
    }


@router.get("/download")
def download_predictions_csv(settings: Settings = Depends(get_settings)) -> FileResponse:  # noqa: B008
    if not settings.predictions_path.exists():
        raise HTTPException(status_code=404, detail="predictions.csv not found")
    return FileResponse(
        path=settings.predictions_path,
        filename="predictions.csv",
        media_type="text/csv",
    )

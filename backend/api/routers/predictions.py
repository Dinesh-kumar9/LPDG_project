"""
API endpoints for Gateway Predictions.
"""

from __future__ import annotations

import pathlib
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
import pandas as pd

from api.dependencies import Settings, get_settings
from src.load import load_gateway_master, normalize_gateway_id
from src.predict import predict

router = APIRouter(prefix="/api/predictions", tags=["Predictions"])


@router.get("")
def get_predictions(
    week_start: Optional[str] = Query(None, description="Filter by Monday date YYYY-MM-DD"),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    pred_path = settings.predictions_path
    if not pred_path.exists():
        # Generate predictions if not already present
        if not settings.data_dir.exists():
            raise HTTPException(status_code=404, detail="Data directory not found to generate predictions")
        try:
            predict(data_dir=settings.data_dir, out_path=pred_path, models_dir=settings.models_dir)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to generate predictions: {e}")

    df = pd.read_csv(pred_path)

    # Optional enrichment with gateway_master data
    try:
        master_df = load_gateway_master(settings.data_dir)
        master_dict = master_df.set_index("gateway_id").to_dict(orient="index")
    except Exception:
        master_dict = {}

    records = []
    for row in df.itertuples(index=False):
        norm_id = normalize_gateway_id(str(row.gateway_id))
        extra = master_dict.get(norm_id, {})
        records.append({
            "week_start": str(row.week_start),
            "rank": int(row.rank),
            "gateway_id": norm_id,
            "score": float(row.score),
            "reason": str(row.reason),
            "site_type": extra.get("site_type"),
            "region": extra.get("region"),
            "hw_model": extra.get("hw_model"),
            "n_meters_installed": extra.get("n_meters_installed"),
        })

    if week_start:
        records = [r for r in records if r["week_start"] == week_start]

    weeks = sorted(df["week_start"].unique().tolist())

    return {
        "total_rows": len(records),
        "available_weeks": weeks,
        "selected_week": week_start,
        "predictions": records,
    }


@router.get("/download")
def download_predictions_csv(settings: Settings = Depends(get_settings)) -> FileResponse:
    if not settings.predictions_path.exists():
        raise HTTPException(status_code=404, detail="predictions.csv not found")
    return FileResponse(
        path=settings.predictions_path,
        filename="predictions.csv",
        media_type="text/csv",
    )

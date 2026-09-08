"""Portable end-to-end checks that never require the private challenge dataset."""

from __future__ import annotations

import hashlib
import json
import pathlib

import pandas as pd

from src.load import load_telemetry
from src.predict import predict
from src.train import write_model_artifact


def test_portable_training_and_prediction_pipeline(
    synthetic_telemetry_dir: pathlib.Path,
    temp_models_dir: pathlib.Path,
    tmp_path: pathlib.Path,
) -> None:
    """A generated schema-valid batch produces the required deterministic submission shape."""
    telemetry = load_telemetry(synthetic_telemetry_dir)
    artifact_path = write_model_artifact(
        telemetry=telemetry,
        models_dir=temp_models_dir,
        version_name="portable_v1",
        promote=True,
    )

    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert set(artifact["drift_reference"]["schema_columns"]) == set(telemetry.columns)

    first = predict(
        data_dir=synthetic_telemetry_dir,
        out_path=tmp_path / "first.csv",
        models_dir=temp_models_dir,
    )
    second = predict(
        data_dir=synthetic_telemetry_dir,
        out_path=tmp_path / "second.csv",
        models_dir=temp_models_dir,
    )

    assert (
        hashlib.sha256(first.read_bytes()).digest() == hashlib.sha256(second.read_bytes()).digest()
    )
    predictions = pd.read_csv(first)
    assert len(predictions) == 120
    assert list(predictions.columns) == [
        "week_start",
        "rank",
        "gateway_id",
        "score",
        "reason",
    ]
    assert all(
        list(group["rank"]) == list(range(1, 16)) for _, group in predictions.groupby("week_start")
    )

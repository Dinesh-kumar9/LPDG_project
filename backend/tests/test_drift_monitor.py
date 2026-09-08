"""
Unit tests for drift monitor (src/drift_monitor.py).
"""

from __future__ import annotations

import pathlib

import pandas as pd

from src.drift_monitor import count_consecutive_flags, run_drift_check
from src.load import load_telemetry
from src.train import write_model_artifact


def test_drift_monitor_clean_data(
    real_data_dir: pathlib.Path,
    temp_models_dir: pathlib.Path,
    temp_reports_dir: pathlib.Path,
):
    telemetry = load_telemetry(real_data_dir)
    write_model_artifact(
        telemetry=telemetry,
        models_dir=temp_models_dir,
        version_name="v1_ref",
        promote=True,
    )

    report = run_drift_check(
        data_dir=real_data_dir,
        reports_dir=temp_reports_dir,
        models_dir=temp_models_dir,
    )

    assert report.drift_flagged is False
    assert report.missing_columns == []
    assert report.new_columns == []
    assert count_consecutive_flags(temp_reports_dir) == 0


def test_drift_monitor_reports_schema_and_range_changes(
    synthetic_telemetry_dir: pathlib.Path,
    temp_models_dir: pathlib.Path,
    temp_reports_dir: pathlib.Path,
):
    """A malformed batch is reported as drift rather than crashing the monitor."""
    telemetry = load_telemetry(synthetic_telemetry_dir)
    write_model_artifact(
        telemetry=telemetry,
        models_dir=temp_models_dir,
        version_name="v1_ref",
        promote=True,
    )

    telemetry_path = next((synthetic_telemetry_dir / "telemetry").rglob("*.parquet"))
    changed = pd.read_parquet(telemetry_path)
    changed["unexpected_metric"] = 1
    changed = changed.drop(columns=["reboot_cnt"])
    changed.to_parquet(telemetry_path, index=False)

    report = run_drift_check(
        data_dir=synthetic_telemetry_dir,
        reports_dir=temp_reports_dir,
        models_dir=temp_models_dir,
    )

    assert report.drift_flagged is True
    assert report.missing_columns == ["reboot_cnt"]
    assert report.new_columns == ["unexpected_metric"]


def test_drift_monitor_reports_historical_range_breach(
    synthetic_telemetry_dir: pathlib.Path,
    temp_models_dir: pathlib.Path,
    temp_reports_dir: pathlib.Path,
):
    """A value above the saved training maximum is detected in a later batch."""
    telemetry = load_telemetry(synthetic_telemetry_dir)
    write_model_artifact(
        telemetry=telemetry,
        models_dir=temp_models_dir,
        version_name="v1_ref",
        promote=True,
    )

    telemetry_path = next((synthetic_telemetry_dir / "telemetry").rglob("*.parquet"))
    changed = pd.read_parquet(telemetry_path)
    changed.loc[changed.index[0], "offline_duration_sec"] = 10_000.0
    expected_gateway = changed.loc[changed.index[0], "gateway_id"]
    changed.to_parquet(telemetry_path, index=False)

    report = run_drift_check(
        data_dir=synthetic_telemetry_dir,
        reports_dir=temp_reports_dir,
        models_dir=temp_models_dir,
    )

    assert report.drift_flagged is True
    assert report.out_of_range_metrics["offline_duration_sec"] == [expected_gateway]

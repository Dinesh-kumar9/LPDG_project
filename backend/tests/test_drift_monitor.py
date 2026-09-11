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


def test_silent_gateways_detected(
    synthetic_telemetry_dir: pathlib.Path,
    temp_models_dir: pathlib.Path,
    temp_reports_dir: pathlib.Path,
):
    """
    A gateway known at training time but silent in the last 7 days must appear
    in silent_gateways. Critically, it must NOT set drift_flagged — the check
    is advisory only, not a data-quality signal (DECISIONS.md ADR 0009 / FAQ 7.1).

    The 3-sigma scoring model is structurally blind to total silence: a gateway
    with zero recent rows scores 0 and falls below rank 15 without any warning.
    This test verifies that the drift monitor makes that gap visible.
    """
    # Train on full synthetic data so gone_quiet_id is in known_gateway_ids.
    telemetry = load_telemetry(synthetic_telemetry_dir)
    write_model_artifact(
        telemetry=telemetry,
        models_dir=temp_models_dir,
        version_name="v1_ref",
        promote=True,
    )

    # Pick one gateway and shift ALL its timestamps 14 days into the past so it
    # has zero rows in the last 7 days but is still present in the parquet file
    # (simulating a gateway that went quiet recently, not one that was deleted).
    telemetry_path = next((synthetic_telemetry_dir / "telemetry").rglob("*.parquet"))
    df = pd.read_parquet(telemetry_path)
    gone_quiet_id = str(df["gateway_id"].iloc[0])
    mask = df["gateway_id"] == gone_quiet_id
    df.loc[mask, "ts_utc"] = pd.to_datetime(df.loc[mask, "ts_utc"]) - pd.Timedelta(days=14)
    df.to_parquet(telemetry_path, index=False)

    report = run_drift_check(
        data_dir=synthetic_telemetry_dir,
        reports_dir=temp_reports_dir,
        models_dir=temp_models_dir,
    )

    # The gone-quiet gateway must be visible in the drift report.
    assert gone_quiet_id in report.silent_gateways, (
        f"Expected {gone_quiet_id} in silent_gateways, got {report.silent_gateways}"
    )
    assert report.silent_gateway_count >= 1

    # CRITICAL: silent gateways are advisory only — drift_flagged must be False.
    # Setting it True would increment the retrain counter for a scenario that
    # may be a decommission, not a data quality problem.
    assert report.drift_flagged is False, (
        "silent_gateways should NOT set drift_flagged — see ADR 0009"
    )


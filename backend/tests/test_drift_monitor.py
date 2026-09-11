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
        telemetry=telemetry, models_dir=temp_models_dir, version_name="v1_ref", promote=True
    )
    report = run_drift_check(
        data_dir=real_data_dir, reports_dir=temp_reports_dir, models_dir=temp_models_dir
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
        telemetry=telemetry, models_dir=temp_models_dir, version_name="v1_ref", promote=True
    )
    telemetry_path = next((synthetic_telemetry_dir / "telemetry").rglob("*.parquet"))
    changed = pd.read_parquet(telemetry_path)
    changed["unexpected_metric"] = 1
    changed = changed.drop(columns=["reboot_cnt"])
    changed.to_parquet(telemetry_path, index=False)
    report = run_drift_check(
        data_dir=synthetic_telemetry_dir, reports_dir=temp_reports_dir, models_dir=temp_models_dir
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
        telemetry=telemetry, models_dir=temp_models_dir, version_name="v1_ref", promote=True
    )
    telemetry_path = next((synthetic_telemetry_dir / "telemetry").rglob("*.parquet"))
    changed = pd.read_parquet(telemetry_path)
    changed.loc[changed.index[0], "offline_duration_sec"] = 10_000.0
    expected_gateway = changed.loc[changed.index[0], "gateway_id"]
    changed.to_parquet(telemetry_path, index=False)
    report = run_drift_check(
        data_dir=synthetic_telemetry_dir, reports_dir=temp_reports_dir, models_dir=temp_models_dir
    )
    assert report.drift_flagged is True
    assert report.out_of_range_metrics["offline_duration_sec"] == [expected_gateway]


# --- Fix 4: Strengthened silent gateway test ---


def test_silent_gateways_detected(
    synthetic_telemetry_dir: pathlib.Path,
    temp_models_dir: pathlib.Path,
    temp_reports_dir: pathlib.Path,
):
    """
    Fix 1+4: A gateway silent for >7 days (relative to data max(ts)) must
    appear in silent_gateways. Asserts EXACT population (not just >= 1).
    """
    telemetry = load_telemetry(synthetic_telemetry_dir)
    write_model_artifact(
        telemetry=telemetry, models_dir=temp_models_dir, version_name="v1_ref", promote=True
    )

    telemetry_path = next((synthetic_telemetry_dir / "telemetry").rglob("*.parquet"))
    df = pd.read_parquet(telemetry_path)
    gone_quiet_id = str(df["gateway_id"].iloc[0])
    mask = df["gateway_id"] == gone_quiet_id
    df.loc[mask, "ts_utc"] = pd.to_datetime(df.loc[mask, "ts_utc"]) - pd.Timedelta(days=14)
    df.to_parquet(telemetry_path, index=False)

    report = run_drift_check(
        data_dir=synthetic_telemetry_dir, reports_dir=temp_reports_dir, models_dir=temp_models_dir
    )

    assert report.silent_gateways == [
        gone_quiet_id
    ], f"Expected [{gone_quiet_id}], got {report.silent_gateways}"
    assert report.silent_gateway_count == 1
    assert report.drift_flagged is False, "silent_gateways must NOT set drift_flagged (ADR 0009)"


# --- Fix 1: Historical data regression tests ---


def test_historical_data_no_false_silent(
    synthetic_telemetry_dir: pathlib.Path,
    temp_models_dir: pathlib.Path,
    temp_reports_dir: pathlib.Path,
):
    """
    Fix 1 regression: historical data ending March 2026, run in September 2026,
    must NOT classify all gateways as silent. Cutoff must be data-anchored.
    """
    telemetry = load_telemetry(synthetic_telemetry_dir)
    write_model_artifact(
        telemetry=telemetry, models_dir=temp_models_dir, version_name="v1_ref", promote=True
    )
    report = run_drift_check(
        data_dir=synthetic_telemetry_dir, reports_dir=temp_reports_dir, models_dir=temp_models_dir
    )
    assert (
        report.silent_gateways == []
    ), f"Expected no silent gateways, got {report.silent_gateways}"
    assert report.silent_gateway_count == 0
    assert report.drift_flagged is False


def test_active_gateways_not_falsely_silent(
    synthetic_telemetry_dir: pathlib.Path,
    temp_models_dir: pathlib.Path,
    temp_reports_dir: pathlib.Path,
):
    """All 15 gateways reporting up to max(ts) -- none should be silent."""
    telemetry = load_telemetry(synthetic_telemetry_dir)
    write_model_artifact(
        telemetry=telemetry, models_dir=temp_models_dir, version_name="v1_ref", promote=True
    )
    report = run_drift_check(
        data_dir=synthetic_telemetry_dir, reports_dir=temp_reports_dir, models_dir=temp_models_dir
    )
    assert report.silent_gateway_count == 0
    assert report.silent_gateways == []


def test_week_start_is_data_anchored(
    synthetic_telemetry_dir: pathlib.Path,
    temp_models_dir: pathlib.Path,
    temp_reports_dir: pathlib.Path,
):
    """Fix 8: week_start must be derived from data max(ts), not wall clock. Data ends 2026-03-23 (Monday)."""
    telemetry = load_telemetry(synthetic_telemetry_dir)
    write_model_artifact(
        telemetry=telemetry, models_dir=temp_models_dir, version_name="v1_ref", promote=True
    )
    report = run_drift_check(
        data_dir=synthetic_telemetry_dir, reports_dir=temp_reports_dir, models_dir=temp_models_dir
    )
    assert report.week_start == "2026-03-23", f"Expected '2026-03-23', got {report.week_start!r}"


# --- Fix 3: Schema-safety tests ---


def _train_ref(synthetic_telemetry_dir: pathlib.Path, temp_models_dir: pathlib.Path) -> None:
    telemetry = load_telemetry(synthetic_telemetry_dir)
    write_model_artifact(
        telemetry=telemetry, models_dir=temp_models_dir, version_name="v1_schema_ref", promote=True
    )


def test_missing_gateway_id_produces_report_not_crash(
    synthetic_telemetry_dir: pathlib.Path,
    temp_models_dir: pathlib.Path,
    temp_reports_dir: pathlib.Path,
):
    """Fix 3: Missing gateway_id must produce a drift report, not KeyError."""
    _train_ref(synthetic_telemetry_dir, temp_models_dir)
    telemetry_path = next((synthetic_telemetry_dir / "telemetry").rglob("*.parquet"))
    df = pd.read_parquet(telemetry_path)
    df.drop(columns=["gateway_id"]).to_parquet(telemetry_path, index=False)
    report = run_drift_check(
        data_dir=synthetic_telemetry_dir, reports_dir=temp_reports_dir, models_dir=temp_models_dir
    )
    assert report.drift_flagged is True
    assert "gateway_id" in report.missing_columns


def test_missing_ts_produces_report_not_crash(
    synthetic_telemetry_dir: pathlib.Path,
    temp_models_dir: pathlib.Path,
    temp_reports_dir: pathlib.Path,
):
    """Fix 3: Missing ts_utc must produce a drift report, not crash."""
    _train_ref(synthetic_telemetry_dir, temp_models_dir)
    telemetry_path = next((synthetic_telemetry_dir / "telemetry").rglob("*.parquet"))
    df = pd.read_parquet(telemetry_path)
    df.drop(columns=["ts_utc"]).to_parquet(telemetry_path, index=False)
    report = run_drift_check(
        data_dir=synthetic_telemetry_dir, reports_dir=temp_reports_dir, models_dir=temp_models_dir
    )
    assert report.drift_flagged is True
    assert len(report.missing_columns) > 0


def test_missing_metric_column_produces_report_not_crash(
    synthetic_telemetry_dir: pathlib.Path,
    temp_models_dir: pathlib.Path,
    temp_reports_dir: pathlib.Path,
):
    """Fix 3: Missing offline_duration_sec must produce a drift report, not crash."""
    _train_ref(synthetic_telemetry_dir, temp_models_dir)
    telemetry_path = next((synthetic_telemetry_dir / "telemetry").rglob("*.parquet"))
    df = pd.read_parquet(telemetry_path)
    df.drop(columns=["offline_duration_sec"]).to_parquet(telemetry_path, index=False)
    report = run_drift_check(
        data_dir=synthetic_telemetry_dir, reports_dir=temp_reports_dir, models_dir=temp_models_dir
    )
    assert report.drift_flagged is True
    assert "offline_duration_sec" in report.missing_columns


def test_multiple_missing_columns_produces_report(
    synthetic_telemetry_dir: pathlib.Path,
    temp_models_dir: pathlib.Path,
    temp_reports_dir: pathlib.Path,
):
    """Fix 3: All missing columns reported; drift_flagged must be True."""
    _train_ref(synthetic_telemetry_dir, temp_models_dir)
    telemetry_path = next((synthetic_telemetry_dir / "telemetry").rglob("*.parquet"))
    df = pd.read_parquet(telemetry_path)
    df.drop(columns=["offline_duration_sec", "disconnection_cnt", "reboot_cnt"]).to_parquet(
        telemetry_path, index=False
    )
    report = run_drift_check(
        data_dir=synthetic_telemetry_dir, reports_dir=temp_reports_dir, models_dir=temp_models_dir
    )
    assert report.drift_flagged is True
    assert "offline_duration_sec" in report.missing_columns
    assert "disconnection_cnt" in report.missing_columns
    assert "reboot_cnt" in report.missing_columns

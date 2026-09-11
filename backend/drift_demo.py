"""
drift_demo.py — Synthetic drift demo for LPDG MLOps pipeline.

Creates a temporary telemetry parquet directory with a renamed column
(schema drift: 'offline_duration_sec' → 'offline_sec_renamed'), then
runs the drift monitor against it to produce a real drift report.

Usage:
  cd backend
  python drift_demo.py
"""

from __future__ import annotations

import datetime as dt
import pathlib
import sys
import tempfile

import pandas as pd

# ── Ensure src/ is importable ─────────────────────────────────────────────────
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from src.drift_monitor import run_drift_check

# ── Synthetic telemetry columns ───────────────────────────────────────────────
KNOWN_GATEWAY_IDS = [
    "0202CB0A6B1F",
    "02043B6BA08B",
    "02075B45BF24",
    "02091DF7CCB8",
    "02097AB58D3C",
    "020CC6FB9659",
    "02132677328F",
    "021491BAAD65",
]

ALL_TELEMETRY_COLS = [
    "gateway_id",
    "ts_utc",
    "offline_duration_sec",
    "disconnection_cnt",
    "reboot_cnt",
    "rssi_good",
    "rssi_normal",
    "rssi_bad",
    "rscp_rsrp_good",
    "rscp_rsrp_normal",
    "rscp_rsrp_bad",
    "network_2g",
    "network_3g",
    "network_4g",
    "rx_nr_pkts",
    "rx_crc_bad",
    "reboot_importance",
    "no_conn_importance",
    "avg_load1",
    "avg_memfree",
]


def _make_synthetic_df(rename_col: str | None = None) -> pd.DataFrame:
    """Build a minimal synthetic telemetry DataFrame."""
    rows = []
    base_ts = pd.Timestamp("2026-03-01 00:00:00", tz="UTC")
    for gw in KNOWN_GATEWAY_IDS:
        for hour in range(24):
            row: dict = {
                "gateway_id": gw,
                "ts_utc": (base_ts + pd.Timedelta(hours=hour)).isoformat(),
                "offline_duration_sec": 0.0,
                "disconnection_cnt": 0.0,
                "reboot_cnt": 0.0,
                "rssi_good": 0.8,
                "rssi_normal": 0.15,
                "rssi_bad": 0.05,
                "rscp_rsrp_good": 0.7,
                "rscp_rsrp_normal": 0.2,
                "rscp_rsrp_bad": 0.1,
                "network_2g": 0.0,
                "network_3g": 0.1,
                "network_4g": 0.9,
                "rx_nr_pkts": 100.0,
                "rx_crc_bad": 1.0,
                "reboot_importance": 0.5,
                "no_conn_importance": 0.3,
                "avg_load1": 0.4,
                "avg_memfree": 1024.0,
            }
            rows.append(row)
    df = pd.DataFrame(rows)
    if rename_col:
        old_name, new_name = rename_col
        df = df.rename(columns={old_name: new_name})
        print(f"  [DEMO] Renamed column '{old_name}' -> '{new_name}' to simulate schema drift")
    return df


def run_demo(reports_dir: pathlib.Path, models_dir: pathlib.Path) -> None:
    """Run a schema-drift demo using synthetic data."""

    with tempfile.TemporaryDirectory(prefix="lpdg_drift_demo_") as tmpdir:
        tmp = pathlib.Path(tmpdir)

        # Create telemetry/ subdir with a parquet partition
        tel_dir = tmp / "telemetry" / "month=2026-03"
        tel_dir.mkdir(parents=True)

        # Build drifted dataframe: rename 'offline_duration_sec' → 'offline_sec_v2'
        drifted_df = _make_synthetic_df(rename_col=("offline_duration_sec", "offline_sec_v2"))
        parquet_path = tel_dir / "part-0.parquet"
        drifted_df.to_parquet(parquet_path, index=False)
        print(f"  [DEMO] Wrote {len(drifted_df)} rows to {parquet_path}")

        # Run drift monitor
        print("\n  [DEMO] Running drift monitor against schema-drifted data...")
        report = run_drift_check(
            data_dir=tmp,
            reports_dir=reports_dir,
            models_dir=models_dir,
            version_id=None,  # defaults to ACTIVE
        )

    # Print report summary
    print(f"\n  drift_flagged : {report.drift_flagged}")
    print(f"  summary       : {report.summary}")
    if report.missing_columns:
        print(f"  missing cols  : {report.missing_columns}")
    if report.new_columns:
        print(f"  new cols      : {report.new_columns}")

    # Find the written report file
    today = dt.date.today().isoformat()
    report_path = reports_dir / f"{today}.json"
    if report_path.exists():
        print(f"\n  [OK] Drift report written to: {report_path}")
    else:
        # Could be same-day overwrite; list recent files
        recent = sorted(reports_dir.glob("*.json"))
        if recent:
            print(f"\n  [OK] Latest drift report: {recent[-1]}")

    if not report.drift_flagged:
        print("\n  [WARN] No drift flagged -- check legacy artifact fallback is active")
        print(
            "         (v1 has no drift_reference.schema_columns -> fallback TELEMETRY_REQUIRED_COLS)"
        )
        print("         With the legacy fallback, 'new columns' are not reported (by design).")
        print("         The missing column 'offline_duration_sec' SHOULD be flagged.")
    else:
        print("\n  [PASS] Schema drift correctly detected and reported.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run schema-drift demo for LPDG MLOps pipeline")
    parser.add_argument(
        "--reports-dir",
        type=pathlib.Path,
        default=pathlib.Path(__file__).resolve().parent.parent / "drift_reports",
    )
    parser.add_argument(
        "--models-dir",
        type=pathlib.Path,
        default=pathlib.Path(__file__).resolve().parent / "models",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("LPDG Drift Monitor — Schema Drift Demo")
    print("=" * 60)
    run_demo(reports_dir=args.reports_dir, models_dir=args.models_dir)
    print("=" * 60)

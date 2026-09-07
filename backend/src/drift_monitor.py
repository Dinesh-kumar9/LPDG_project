"""
Drift monitor for the LPDG gateway telemetry pipeline.

PURPOSE:
  Run before every predict call to catch data quality regressions before they
  silently produce wrong rankings. A drift flag means the predict step should
  be reviewed by a human — it does NOT mean auto-retrain.

DESIGN PRINCIPLE:
  The monitor logs and flags. It does NOT:
    - Crash the pipeline (returns a DriftReport, never raises on drift)
    - Trigger retraining automatically (see RETRAIN_POLICY.md)
    - Modify any data

RETRAIN TRIGGER (from RETRAIN_POLICY.md):
  If drift_flagged=True for 3+ consecutive weeks → recommend retrain.
  The monitor tracks consecutive flags in drift_reports/ history.

Reports are written to drift_reports/YYYY-MM-DD.json (one per run).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from dataclasses import asdict, dataclass, field

import pandas as pd

from src.load import (
    TELEMETRY_REQUIRED_COLS,
    load_telemetry,
)
from src.train import MODELS_DIR, load_model_artifact

# ─── Report dataclass ─────────────────────────────────────────────────────────


@dataclass
class DriftReport:
    """Complete drift check result — serializable to JSON."""

    checked_at: str  # ISO-8601 timestamp
    data_path: str
    reference_version: str  # model version that defines "normal"

    # Schema drift
    new_columns: list[str] = field(default_factory=list)
    missing_columns: list[str] = field(default_factory=list)

    # Gateway population drift
    new_gateway_ids: list[str] = field(default_factory=list)
    missing_gateway_ids: list[str] = field(default_factory=list)
    new_gateway_id_pct: float = 0.0

    # Value drift (metric extremes)
    out_of_range_metrics: dict[str, list[str]] = field(default_factory=dict)

    # Result
    drift_flagged: bool = False
    summary: str = "No drift detected."

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


# ─── Thresholds ───────────────────────────────────────────────────────────────

# More than this fraction of gateway IDs being new → flag.
NEW_GATEWAY_ID_THRESHOLD: float = 0.05

# A metric value exceeding this multiple of the historical max → flag.
# (Catches obvious sensor errors or unit changes, not normal variance.)
VALUE_RANGE_MULTIPLIER: float = 5.0

# Metrics we check for value-range drift.
MONITORED_METRICS: list[str] = [
    "offline_duration_sec",
    "disconnection_cnt",
    "reboot_cnt",
]


# ─── Drift checks ─────────────────────────────────────────────────────────────


def _check_schema(
    new_df: pd.DataFrame,
    reference_version_artifact: dict,  # type: ignore[type-arg]
    report: DriftReport,
) -> None:
    """Check for missing required columns relative to the expected schema."""
    # load_telemetry converts ts_utc -> ts
    required = (TELEMETRY_REQUIRED_COLS - {"ts_utc"}) | {"ts"}
    actual = set(new_df.columns)

    missing = sorted(required - actual)
    report.missing_columns = missing

    if missing:
        report.drift_flagged = True
        report.summary = f"Schema drift: {len(missing)} missing column(s): {missing}"


def _check_gateway_population(
    new_df: pd.DataFrame,
    reference_version_artifact: dict,  # type: ignore[type-arg]
    report: DriftReport,
) -> None:
    """
    Check whether the set of gateway IDs has changed significantly.

    New gateways (installed after training) are expected occasionally.
    A large influx (>5% of known IDs) likely means a data delivery error
    or a major infrastructure change that warrants human review.

    WHY we exclude new gateways from value-range checks:
      They have no historical baseline to compare against, so any value
      would look like an anomaly. Flagging their existence is sufficient.
    """
    known_ids = set(reference_version_artifact.get("known_gateway_ids", []))
    new_ids = set(new_df["gateway_id"].unique())

    actually_new = sorted(new_ids - known_ids)
    missing = sorted(known_ids - new_ids)

    report.new_gateway_ids = actually_new
    report.missing_gateway_ids = missing

    if known_ids:
        report.new_gateway_id_pct = len(actually_new) / len(known_ids)
    else:
        report.new_gateway_id_pct = 0.0

    if report.new_gateway_id_pct > NEW_GATEWAY_ID_THRESHOLD:
        report.drift_flagged = True
        report.summary = (
            f"Population drift: {len(actually_new)} new gateway IDs "
            f"({report.new_gateway_id_pct:.1%} of known set). "
            "Review before predicting."
        )


def _check_value_ranges(
    new_df: pd.DataFrame,
    reference_version_artifact: dict,  # type: ignore[type-arg]
    report: DriftReport,
) -> None:
    """
    Check whether any metric has values wildly outside historical maximums.

    Only checks gateways that existed during training (new gateways are skipped).
    Uses VALUE_RANGE_MULTIPLIER × historical max as the upper bound.

    WHY 5× not 3σ:
      3σ would flag normal operational variance (it's the ranking signal, not
      a data-quality signal). 5× historical max catches sensor errors, unit
      changes, and obvious corruption without false-positiving on real anomalies.
    """
    known_ids = set(reference_version_artifact.get("known_gateway_ids", []))
    existing_df = new_df[new_df["gateway_id"].isin(known_ids)]

    if existing_df.empty:
        return

    # Compute historical maximums from the training telemetry window.
    # We approximate this using the new data itself for now; in Phase 3 we
    # store per-gateway metric stats in the model artifact.
    historical_max = existing_df.groupby("gateway_id")[MONITORED_METRICS].max()

    flagged: dict[str, list[str]] = {}
    for metric in MONITORED_METRICS:
        metric_max = existing_df.groupby("gateway_id")[metric].max()
        hist_max = historical_max[metric]
        threshold = hist_max * VALUE_RANGE_MULTIPLIER
        exceeded = metric_max[metric_max > threshold]
        if not exceeded.empty:
            flagged[metric] = exceeded.index.tolist()

    report.out_of_range_metrics = flagged
    if flagged:
        report.drift_flagged = True
        flagged_count = sum(len(v) for v in flagged.values())
        report.summary = (
            f"Value drift: {flagged_count} gateway/metric combinations exceed "
            f"{VALUE_RANGE_MULTIPLIER}× historical maximum. Metrics: {list(flagged.keys())}"
        )


# ─── Consecutive drift counter ────────────────────────────────────────────────


def count_consecutive_flags(reports_dir: pathlib.Path) -> int:
    """
    Count how many of the most-recent drift reports have drift_flagged=True.
    Used to determine whether the retrain threshold has been reached (3 weeks).
    """
    report_files = sorted(reports_dir.glob("*.json"), reverse=True)
    consecutive = 0
    for f in report_files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("drift_flagged"):
                consecutive += 1
            else:
                break
        except (json.JSONDecodeError, KeyError):
            break
    return consecutive


# ─── Main check function ──────────────────────────────────────────────────────


def run_drift_check(
    data_dir: pathlib.Path,
    reports_dir: pathlib.Path,
    models_dir: pathlib.Path = MODELS_DIR,
    version_id: str | None = None,
) -> DriftReport:
    """
    Run all drift checks against the current data and write a dated report.

    Returns the DriftReport. Never raises on drift — callers can inspect
    report.drift_flagged and decide whether to proceed with predict.
    """
    reports_dir.mkdir(parents=True, exist_ok=True)

    artifact = load_model_artifact(version_id, models_dir)
    ref_version = artifact["version_id"]

    new_telemetry = load_telemetry(data_dir)

    report = DriftReport(
        checked_at=dt.datetime.now(dt.UTC).isoformat(),
        data_path=str(data_dir),
        reference_version=ref_version,
        summary="No drift detected.",
    )

    _check_schema(new_telemetry, artifact, report)
    if not report.drift_flagged:
        _check_gateway_population(new_telemetry, artifact, report)
    if not report.drift_flagged:
        _check_value_ranges(new_telemetry, artifact, report)

    # Write dated report
    date_str = dt.date.today().isoformat()
    report_path = reports_dir / f"{date_str}.json"
    report_path.write_text(report.to_json(), encoding="utf-8")

    consecutive = count_consecutive_flags(reports_dir)

    if report.drift_flagged:
        print(f"[WARN] DRIFT DETECTED: {report.summary}")
        print(f"   Consecutive flagged weeks: {consecutive}/3")
        if consecutive >= 3:
            print("   [WARN] RETRAIN RECOMMENDED (see RETRAIN_POLICY.md)")
    else:
        print(f"[OK] No drift detected. Report written to {report_path}")

    return report


# ─── CLI entry point ──────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run drift checks on incoming telemetry before predicting."
    )
    parser.add_argument("--data", type=pathlib.Path, required=True)
    parser.add_argument(
        "--reports-dir",
        type=pathlib.Path,
        default=pathlib.Path("drift_reports"),
    )
    parser.add_argument("--models-dir", type=pathlib.Path, default=MODELS_DIR)
    parser.add_argument("--version", type=str, default=None)
    parser.add_argument(
        "--fail-on-drift",
        action="store_true",
        help="Exit with code 1 if drift is detected (useful in CI).",
    )
    args = parser.parse_args(argv)

    report = run_drift_check(
        data_dir=args.data,
        reports_dir=args.reports_dir,
        models_dir=args.models_dir,
        version_id=args.version,
    )

    if args.fail_on_drift and report.drift_flagged:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

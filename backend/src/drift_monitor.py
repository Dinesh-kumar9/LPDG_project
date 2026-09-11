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

    # Gone-quiet gateways (known at training time, zero rows in recent window)
    # These do NOT set drift_flagged — they are advisory for human review.
    # See DECISIONS.md ADR 0009 and FAQ 7.1.
    silent_gateways: list[str] = field(default_factory=list)
    silent_gateway_count: int = 0

    # Explicit week identifier derived from the data's own latest timestamp.
    # Use this instead of relying on the report file's wall-clock date for
    # period-aware consecutive-flag counting.
    week_start: str = ""  # ISO date of the Monday of the most recent data week

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

# Trailing window used to detect gone-quiet gateways — matches predict.py's
# DEFAULT_RECENT_DAYS so the check is consistent with the scoring boundary.
SILENT_GATEWAY_RECENT_DAYS: int = 7


# ─── Drift checks ─────────────────────────────────────────────────────────────


def _check_schema(
    new_df: pd.DataFrame,
    reference_version_artifact: dict,  # type: ignore[type-arg]
    report: DriftReport,
) -> None:
    """Check the incoming column set against the training-time reference."""
    # New artifacts store the complete normalized telemetry schema.  Existing
    # artifacts predate that field, so retain a safe required-column fallback.
    reference = reference_version_artifact.get("drift_reference", {})
    reference_columns = reference.get("schema_columns", [])
    required = set(reference_columns)
    if not required:
        required = set((TELEMETRY_REQUIRED_COLS - {"ts_utc"}) | {"ts"})
    actual = set(new_df.columns)

    missing = sorted(required - actual)
    # A legacy artifact has no complete training schema, so optional telemetry
    # fields must not be misclassified as newly introduced columns.
    new = sorted(actual - required) if reference_columns else []
    report.missing_columns = missing
    report.new_columns = new

    if missing or new:
        report.drift_flagged = True
        report.summary = (
            f"Schema drift: {len(missing)} missing column(s), {len(new)} new column(s). "
            f"Missing: {missing}; new: {new}"
        )


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
    # Guard: schema drift already flagged missing gateway_id — skip safely.
    if "gateway_id" not in new_df.columns:
        return
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
    # Guard: schema drift already flagged missing gateway_id — skip safely.
    if "gateway_id" not in new_df.columns:
        return
    known_ids = set(reference_version_artifact.get("known_gateway_ids", []))
    existing_df = new_df[new_df["gateway_id"].isin(known_ids)]

    if existing_df.empty:
        return

    reference = reference_version_artifact.get("drift_reference", {})
    historical_maxima = reference.get("metric_maxima", {})
    if not historical_maxima:
        # Legacy artifacts do not contain training-time maxima.  Do not invent
        # a baseline from the incoming data; schema and population checks still
        # run, while full range monitoring begins after the next training run.
        return

    flagged: dict[str, list[str]] = {}
    for metric in MONITORED_METRICS:
        historical_max = historical_maxima.get(metric)
        if historical_max is None or metric not in existing_df.columns:
            continue
        threshold = float(historical_max) * VALUE_RANGE_MULTIPLIER
        exceeded_ids = existing_df.loc[existing_df[metric] > threshold, "gateway_id"].unique()
        if len(exceeded_ids):
            flagged[metric] = sorted(str(gateway_id) for gateway_id in exceeded_ids)

    report.out_of_range_metrics = flagged
    if flagged:
        report.drift_flagged = True
        flagged_count = sum(len(v) for v in flagged.values())
        report.summary = (
            f"Value drift: {flagged_count} gateway/metric combinations exceed "
            f"{VALUE_RANGE_MULTIPLIER}× historical maximum. Metrics: {list(flagged.keys())}"
        )


def _check_silent_gateways(
    new_df: pd.DataFrame,
    reference_version_artifact: dict,  # type: ignore[type-arg]
    report: DriftReport,
) -> None:
    """
    Identify gateways that are known (appeared in training) but produced
    zero telemetry rows in the trailing SILENT_GATEWAY_RECENT_DAYS window.

    WHY this is not caught by 3-sigma scoring (FAQ 7.1):
      rank_week() scores only hours that EXIST in the recent window.
      A gateway with zero rows contributes nothing to the flagged_hours sum
      and scores 0. It silently falls below rank 15 — the highest-urgency
      failure case (a dead gateway costs €600/week) is structurally invisible
      to the baseline. See DECISIONS.md ADR 0009.

    WHY we anchor to the data's latest timestamp, not the system clock:
      The challenge data ends March 2026. Running the monitor in September 2026
      with a wall-clock anchor would classify ALL gateways as silent (zero rows
      in the last 7 real-world days). Using max(ts) from the incoming telemetry
      ensures the window is always relative to the data being evaluated.

    WHY we log rather than inject a score:
      Total silence is ambiguous: hardware death, data pipeline failure, or
      an unnotified decommission are all possible. Fabricating a score treats
      all three identically. Surfacing the list lets a human with operational
      context decide. FAQ 7.1 bar: not 'in the top 15' but 'you noticed it'.

    DOES NOT set drift_flagged — silent gateways are an operational advisory,
    not a data quality signal that should block prediction or increment the
    consecutive-flag counter toward the retrain threshold.
    """
    # Guard: if required columns are missing, schema drift is already flagged.
    if "gateway_id" not in new_df.columns or "ts" not in new_df.columns:
        return

    known_ids = set(reference_version_artifact.get("known_gateway_ids", []))
    if not known_ids or new_df.empty:
        return

    # FIX: anchor to the data's own latest timestamp, NOT the system clock.
    # Using pd.Timestamp.now() causes every gateway to appear silent when the
    # challenge's historical data (ending March 2026) is evaluated later.
    latest_ts = new_df["ts"].max()
    if pd.isna(latest_ts):
        return
    cutoff = latest_ts - pd.Timedelta(days=SILENT_GATEWAY_RECENT_DAYS)

    recent_ids = set(new_df[new_df["ts"] >= cutoff]["gateway_id"].unique())

    silent = sorted(known_ids - recent_ids)
    report.silent_gateways = silent
    report.silent_gateway_count = len(silent)

    if silent:
        preview = silent[:5]
        ellipsis = "..." if len(silent) > 5 else ""
        print(
            f"[WARN] {len(silent)} known gateway(s) produced zero telemetry "
            f"in the last {SILENT_GATEWAY_RECENT_DAYS} days (relative to "
            f"data latest={latest_ts.date()}) — they score 0 and cannot "
            "reach the top-15. Check drift report 'silent_gateways' field. "
            f"First five: {preview}{ellipsis}"
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

    # Keep schema validation non-fatal here so a missing or unexpected column
    # becomes an auditable drift report.  Training and prediction use strict
    # validation and will not consume a batch that has been flagged.
    new_telemetry = load_telemetry(data_dir, validate_schema=False)

    # Derive the week_start anchor from the data itself (not the wall clock).
    # This makes the period identifier correct for historical datasets.
    week_start_str = ""
    if not new_telemetry.empty and "ts" in new_telemetry.columns:
        latest_ts = new_telemetry["ts"].max()
        if not pd.isna(latest_ts):
            days_since_monday = latest_ts.weekday()
            monday = (latest_ts - pd.Timedelta(days=days_since_monday)).date()
            week_start_str = monday.isoformat()

    report = DriftReport(
        checked_at=dt.datetime.now(dt.UTC).isoformat(),
        data_path=str(data_dir),
        reference_version=ref_version,
        week_start=week_start_str,
        summary="No drift detected.",
    )

    _check_schema(new_telemetry, artifact, report)
    if not report.drift_flagged:
        _check_gateway_population(new_telemetry, artifact, report)
    if not report.drift_flagged:
        _check_value_ranges(new_telemetry, artifact, report)
    # Silent-gateway check runs regardless of other flags — it is an orthogonal
    # operational advisory and must not be suppressed by a schema/range flag.
    _check_silent_gateways(new_telemetry, artifact, report)

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

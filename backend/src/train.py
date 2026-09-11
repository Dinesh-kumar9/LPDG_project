"""
Versioned model training for the LPDG gateway prioritization pipeline.

DESIGN DECISION (DECISIONS.md #1):
  The scoring logic reuses the 3-sigma baseline from baseline_3sigma.py
  deliberately. The MLOps track grades the engineering *around* the ranking
  logic, not the ranking logic itself. A reproducible, versioned, registry-
  backed pipeline using the baseline beats a sophisticated model in a notebook.

  Phase 3 will introduce XGBoost + SHAP features. The registry architecture
  is identical — only model_type changes in the JSON artifact.

Model artifact (models/vN_<date>.json):
  - Contains ALL parameters needed to reproduce predictions exactly.
  - Stores a SHA-256 hash of the training data for drift/integrity checks.
  - Stores a fixed-slice prediction hash used by rollback.py verify.
  - Training and promotion are SEPARATE steps (--promote flag).
    A bad training run never silently becomes the active version.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import logging
import pathlib
import sys
from typing import Any, Final

import numpy as np
import pandas as pd

from src.load import (
    load_telemetry,
)

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

MODELS_DIR: Final = pathlib.Path("models")
ACTIVE_FILE: Final = MODELS_DIR / "ACTIVE"
ROLLBACK_LOG: Final = MODELS_DIR / "rollback_log.jsonl"

# 3-sigma scoring parameters — default values match the provided baseline.
DEFAULT_SIGMA: Final[float] = 3.0
DEFAULT_BASELINE_DAYS: Final[int] = 28
DEFAULT_RECENT_DAYS: Final[int] = 7
VISITS_PER_WEEK: Final[int] = 15
METRICS: Final[list[str]] = ["offline_duration_sec", "disconnection_cnt", "reboot_cnt"]

# Minimum number of hourly rows a gateway must have in the baseline window
# before its 3-sigma statistics are considered reliable.  Gateways with fewer
# rows are treated as having insufficient history: they are NOT flagged (score=0)
# and are deliberately excluded from the top-15 ranked output.
# Rationale: with < 24 hours of history the per-gateway std is computed from
# too few points to be meaningful; flagging such gateways would be spurious.
# POLICY: this is a deliberate operational choice, NOT a silent accident.
# See DECISIONS.md ADR-0003 for the broader data-quality boundary philosophy.
MIN_BASELINE_HOURS: Final[int] = 24

# Fixed slice used by rollback verify — a Monday well inside the training window.
# Never change this after v1 is deployed; it must stay constant for hash comparison.
VERIFY_SLICE_DATE: Final[dt.date] = dt.date(2025, 11, 3)


# ─── Scoring (3-sigma baseline logic) ────────────────────────────────────────


def rank_week(
    telemetry: pd.DataFrame,
    monday: dt.date,
    sigma: float,
    baseline_days: int,
    recent_days: int,
    min_baseline_hours: int = MIN_BASELINE_HOURS,
) -> tuple[pd.DataFrame, list[str]]:
    """
    Score all gateways for one week using per-gateway 3-sigma anomaly detection.

    Method:
      1. Take the trailing `baseline_days` of telemetry strictly before `monday`.
      2. Compute per-gateway mean and std of each metric in that window.
      3. Flag hours in the trailing `recent_days` where any metric exceeds
         (mean + sigma * std) for that gateway.
      4. Score = total flagged hours across all metrics.

    Returns:
      (ranked_df, excluded_ids) where:
        - ranked_df has columns: gateway_id, flagged_hours, worst_metric
          sorted descending by flagged_hours.
        - excluded_ids lists gateway IDs excluded due to insufficient baseline
          history (fewer than `min_baseline_hours` rows in the baseline window).

    POLICY — insufficient-history exclusion (FAQ 6.11):
      A gateway with < `min_baseline_hours` rows in the baseline window has
      unreliable per-gateway statistics.  Such gateways are EXCLUDED from the
      scored output with a logged warning.  They receive score=0 and are NOT
      silently dropped — callers receive the excluded list so they can surface
      it in monitoring dashboards.  This is a deliberate operational decision,
      not a side-effect of NaN arithmetic.

    WHY per-gateway baselines:
      Different gateways have very different normal behaviour (site type, meters
      served, location). A global threshold would flag rural gateways far more
      than urban ones. Per-gateway baselines make the signal comparable.
    """
    end = pd.Timestamp(monday, tz="UTC")
    # Use datetime.timedelta (stdlib) not pd.Timedelta to avoid NumPy 2.x
    # deprecation warnings that appear in Python 3.12 output.
    baseline_start = end - dt.timedelta(days=baseline_days)
    recent_start = end - dt.timedelta(days=recent_days)

    window = telemetry[(telemetry["ts"] >= baseline_start) & (telemetry["ts"] < end)]
    if window.empty:
        return pd.DataFrame(columns=["gateway_id", "flagged_hours", "worst_metric"]), []

    # ── POLICY: exclude gateways with insufficient baseline history ───────────
    baseline_counts = window.groupby("gateway_id").size()
    insufficient = baseline_counts[baseline_counts < min_baseline_hours].index.tolist()
    # Remove their rows from the baseline stats and recent window so they are
    # fully excluded from scoring — not left with NaN-derived zeros.
    if insufficient:
        window = window[~window["gateway_id"].isin(insufficient)]

    stats = window.groupby("gateway_id")[METRICS].agg(["mean", "std"])
    recent = window[window["ts"] >= recent_start].copy()

    flags = pd.Series(0, index=recent.index, dtype=int)
    worst = pd.Series("", index=recent.index, dtype=object)

    for metric in METRICS:
        mean = recent["gateway_id"].map(stats[(metric, "mean")])
        # Replace std=0 with NaN to avoid division-by-zero producing spurious flags.
        std = recent["gateway_id"].map(stats[(metric, "std")]).replace(0, np.nan)
        exceeded = (recent[metric] - mean) > sigma * std
        exceeded = exceeded.fillna(False)
        flags = flags + exceeded.astype(int)
        # Track which metric first caused a breach (matches baseline_3sigma.py).
        worst = worst.where(~exceeded | (worst != ""), metric)

    recent["flagged"] = flags
    recent["worst_metric"] = worst

    if recent.empty:
        return pd.DataFrame(columns=["gateway_id", "flagged_hours", "worst_metric"]), insufficient

    grouped = recent.groupby("gateway_id").agg(
        flagged_hours=("flagged", "sum"),
        worst_metric=("worst_metric", lambda s: next((v for v in s if v), "")),
    )
    return grouped.sort_values("flagged_hours", ascending=False).reset_index(), insufficient


def score_all_weeks(
    telemetry: pd.DataFrame,
    scored_weeks: list[dt.date],
    sigma: float,
    baseline_days: int,
    recent_days: int,
) -> pd.DataFrame:
    """
    Score all 8 weeks and return a flat DataFrame ready for predict.py.

    Gateways with insufficient baseline history are excluded per the policy
    documented in rank_week.  A WARNING is logged for each week listing the
    excluded IDs so operators can monitor new/quiet gateways.
    """
    rows = []
    for monday in scored_weeks:
        ranked, excluded = rank_week(telemetry, monday, sigma, baseline_days, recent_days)
        if excluded:
            logger.warning(
                "week=%s: %d gateway(s) excluded — insufficient baseline history "
                "(< %d hours in the %d-day window): %s",
                monday.isoformat(),
                len(excluded),
                MIN_BASELINE_HOURS,
                baseline_days,
                excluded,
            )
        if len(ranked) < VISITS_PER_WEEK:
            raise SystemExit(
                f"Only {len(ranked)} gateways have data before {monday}. "
                "Cannot produce 15 ranked gateways."
            )
        top = ranked.head(VISITS_PER_WEEK)
        for rank, rec in enumerate(top.to_dict(orient="records"), 1):
            metric_str = str(rec.get("worst_metric") or "no metric over threshold")
            flagged = rec.get("flagged_hours", 0)
            rows.append(
                {
                    "week_start": monday.isoformat(),
                    "rank": rank,
                    "gateway_id": rec.get("gateway_id"),
                    "score": float(flagged),
                    "reason": (
                        f"{int(flagged)} hour(s) beyond {sigma}\u03c3 of this "
                        f"gateway's own {baseline_days}-day baseline in the last "
                        f"{recent_days} days; first breach on {metric_str}"
                    )[:300],
                }
            )
    return pd.DataFrame(rows)


# ─── Hashing utilities ────────────────────────────────────────────────────────


def _hash_dataframe(df: pd.DataFrame) -> str:
    """SHA-256 hash of a DataFrame's canonical CSV representation."""
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(csv_bytes).hexdigest()


def _serialize_predictions_canonical(predictions: pd.DataFrame) -> bytes:
    """
    Canonical, deterministic byte serialization of a predictions DataFrame.

    This is the SINGLE authoritative serialization used by:
      - compute_verify_hash() (training time)
      - rollback.py verify()
      - predict.py output
      - determinism tests

    Invariants:
      - Rows sorted by week_start ASC, score DESC, gateway_id ASC (tiebreak)
      - rank re-derived from sort order via groupby.cumcount()
      - Exactly 5 columns in fixed order: week_start, rank, gateway_id, score, reason
      - float_format="%.1f" (scores are rendered with exactly 1 decimal place)
      - UTF-8 encoding, Unix newlines from pandas to_csv()

    WHY one canonical path:
      Previously train.py wrote CSVs without float_format and without the
      deterministic re-sort, while rollback.py wrote with float_format but also
      without re-sort, and predict.py applied the sort+re-rank. Three subtly
      different byte streams — but the stored hash only matched one of them.
      This function closes all three gaps.
    """
    df = predictions.copy()
    df = df.sort_values(
        ["week_start", "score", "gateway_id"],
        ascending=[True, False, True],
    ).reset_index(drop=True)
    df["rank"] = df.groupby("week_start").cumcount() + 1
    df = df[["week_start", "rank", "gateway_id", "score", "reason"]]
    return str(df.to_csv(index=False, float_format="%.1f")).encode("utf-8")


def _hash_predictions_canonical(predictions: pd.DataFrame) -> str:
    """SHA-256 over the canonical byte serialization of a predictions DataFrame."""
    return "sha256:" + hashlib.sha256(_serialize_predictions_canonical(predictions)).hexdigest()


def _hash_predictions_csv(path: pathlib.Path) -> str:
    """SHA-256 hash of a predictions CSV file (used for the output file display)."""
    content = path.read_bytes()
    return "sha256:" + hashlib.sha256(content).hexdigest()


# ─── Fixed-slice prediction for rollback verify ───────────────────────────────


def compute_verify_hash(
    telemetry: pd.DataFrame,
    sigma: float,
    baseline_days: int,
    recent_days: int,
    tmp_dir: pathlib.Path,
) -> str:
    """
    Generate predictions for the fixed verify slice and return their hash.

    Uses _hash_predictions_canonical() — the single canonical path shared by
    predict.py output and rollback.py verify(). This ensures:

        training hash == production predict hash == rollback verify hash

    WHY a fixed slice:
      rollback.py verify must prove that the active version produces byte-identical
      output after a rollback. It does this by re-running predict on a fixed,
      immutable input slice and comparing the hash. The slice date (VERIFY_SLICE_DATE)
      must never change after v1 is deployed — if it changes, historical hashes
      become incomparable.
    """
    verify_weeks = [VERIFY_SLICE_DATE]
    predictions = score_all_weeks(telemetry, verify_weeks, sigma, baseline_days, recent_days)
    return _hash_predictions_canonical(predictions)


# ─── Model artifact writer ────────────────────────────────────────────────────


def _next_version_id(version_name: str | None, models_dir: pathlib.Path) -> str:
    """
    Derive a version ID.
    If version_name is given, use it directly (e.g. "v2_broken" for demos).
    Otherwise auto-increment: v1, v2, v3...
    """
    if version_name:
        date_str = dt.date.today().isoformat()
        return f"{version_name}_{date_str}"

    existing = sorted(models_dir.glob("v[0-9]*.json"))
    n = len(existing) + 1
    date_str = dt.date.today().isoformat()
    return f"v{n}_{date_str}"


def write_model_artifact(
    telemetry: pd.DataFrame,
    models_dir: pathlib.Path,
    version_name: str | None = None,
    sigma: float = DEFAULT_SIGMA,
    baseline_days: int = DEFAULT_BASELINE_DAYS,
    recent_days: int = DEFAULT_RECENT_DAYS,
    promote: bool = False,
) -> pathlib.Path:
    """
    Train the model and write a versioned JSON artifact to models_dir.

    The artifact contains:
      - All parameters needed to reproduce predictions exactly.
      - SHA-256 hash of the telemetry DataFrame used for training.
      - SHA-256 hash of a fixed-slice prediction (for rollback verify).
      - The complete list of gateway IDs seen during training (for drift monitor).

    The artifact is written atomically: tmp file → rename.
    ACTIVE is only updated when promote=True.
    """
    models_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = models_dir / "_tmp"
    tmp_dir.mkdir(exist_ok=True)

    version_id = _next_version_id(version_name, models_dir)
    artifact_path = models_dir / f"{version_id}.json"

    if artifact_path.exists():
        raise FileExistsError(
            f"Model artifact already exists: {artifact_path}. "
            "Use a different version name or delete the existing file."
        )

    # Hash the training data so drift monitor can detect input changes.
    training_data_hash = _hash_dataframe(
        telemetry[["gateway_id", "ts"] + METRICS].sort_values(["gateway_id", "ts"])
    )

    # Compute the verify hash for rollback.py verify.
    verify_hash = compute_verify_hash(telemetry, sigma, baseline_days, recent_days, tmp_dir)

    # Collect known gateway IDs for the drift monitor.
    known_gateway_ids = sorted(telemetry["gateway_id"].unique().tolist())

    # Preserve an explicit training-time reference for drift monitoring.  This
    # makes range checks a comparison with the training distribution rather
    # than a tautological comparison with the incoming batch itself.
    drift_reference = {
        "schema_columns": sorted(telemetry.columns.tolist()),
        "metric_maxima": {metric: float(telemetry[metric].max()) for metric in METRICS},
    }

    # Build the scored_weeks list for documentation (not needed at predict time).
    scored_weeks = [(dt.date(2026, 2, 2) + dt.timedelta(days=7 * i)).isoformat() for i in range(8)]

    artifact: dict[str, object] = {
        "version_id": version_id,
        "model_type": "rule_based_3sigma",
        "trained_at": dt.datetime.now(dt.UTC).isoformat(),
        "training_window": {
            "start": telemetry["ts"].min().date().isoformat(),
            "end": telemetry["ts"].max().date().isoformat(),
        },
        "parameters": {
            "sigma": sigma,
            "baseline_days": baseline_days,
            "recent_days": recent_days,
            "metrics": METRICS,
            "visits_per_week": VISITS_PER_WEEK,
        },
        "scored_weeks": scored_weeks,
        "training_data_hash": training_data_hash,
        "fixed_slice_prediction_hash": verify_hash,
        "fixed_slice_date": VERIFY_SLICE_DATE.isoformat(),
        "known_gateway_ids": known_gateway_ids,
        "known_gateway_count": len(known_gateway_ids),
        "drift_reference": drift_reference,
        "promoted": promote,
    }

    # Write atomically: tmp → rename.
    tmp_artifact = tmp_dir / f"{version_id}.json.tmp"
    tmp_artifact.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    tmp_artifact.rename(artifact_path)

    tmp_dir.rmdir() if not any(tmp_dir.iterdir()) else None

    print(f"[OK] Model artifact written: {artifact_path}")

    if promote:
        _set_active(version_id, models_dir)

    return artifact_path


def _set_active(version_id: str, models_dir: pathlib.Path) -> None:
    """Atomically write the ACTIVE pointer file via temporary file replace."""
    active_path = models_dir / "ACTIVE"
    tmp_path = models_dir / f".ACTIVE.{dt.datetime.now(dt.UTC).timestamp()}.tmp"
    tmp_path.write_text(version_id, encoding="utf-8")
    tmp_path.replace(active_path)
    print(f"[OK] ACTIVE -> {version_id}")


def load_model_artifact(
    version_id: str | None, models_dir: pathlib.Path = MODELS_DIR
) -> dict[str, Any]:
    """
    Load a model artifact JSON by version ID.

    If version_id is None, reads the ACTIVE pointer file and uses that version.
    Raises FileNotFoundError if the version doesn't exist (never silently falls back).
    """
    if version_id is None:
        active_path = models_dir / "ACTIVE"
        if not active_path.exists():
            raise FileNotFoundError(
                "No ACTIVE version found. Run `python -m src.train --promote` first."
            )
        version_id = active_path.read_text(encoding="utf-8").strip()

    artifact_path = models_dir / f"{version_id}.json"
    if not artifact_path.exists():
        available = [p.stem for p in models_dir.glob("*.json")]
        raise FileNotFoundError(
            f"Model artifact not found: {artifact_path}\n" f"Available versions: {available}"
        )

    return dict[str, Any](json.loads(artifact_path.read_text(encoding="utf-8")))


# ─── CLI entry point ──────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Train the gateway ranking model and write a versioned artifact."
    )
    parser.add_argument(
        "--data",
        type=pathlib.Path,
        required=True,
        help="Path to the data directory containing telemetry/, gateway_master.csv, etc.",
    )
    parser.add_argument(
        "--models-dir",
        type=pathlib.Path,
        default=MODELS_DIR,
        help="Path to the model registry directory (default: ./models).",
    )
    parser.add_argument(
        "--version",
        type=str,
        default=None,
        help="Version name prefix (e.g. 'v1'). Auto-increments if omitted.",
    )
    parser.add_argument(
        "--sigma",
        type=float,
        default=DEFAULT_SIGMA,
        help=f"Sigma threshold for anomaly detection (default: {DEFAULT_SIGMA}).",
    )
    parser.add_argument(
        "--promote",
        action="store_true",
        help="Set this version as ACTIVE after writing. Omit to train without promoting.",
    )
    args = parser.parse_args(argv)

    print(f"Loading telemetry from {args.data} ...")
    telemetry = load_telemetry(args.data)
    print(f"  Loaded {len(telemetry):,} rows, {telemetry['gateway_id'].nunique()} gateways.")

    write_model_artifact(
        telemetry=telemetry,
        models_dir=args.models_dir,
        version_name=args.version,
        sigma=args.sigma,
        promote=args.promote,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

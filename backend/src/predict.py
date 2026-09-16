"""
Deterministic gateway ranking predictor.

DETERMINISM GUARANTEE:
  Given the same model version JSON + same input data, this module always
  produces byte-identical predictions.csv output. There is no randomness:
  - No random seeds needed (3-sigma is pure arithmetic)
  - Output sort order is deterministic (sort by score desc, gateway_id asc as tiebreak)
  - CSV is written with consistent float formatting

  test_determinism.py enforces this by running predict() twice on the same
  inputs and comparing SHA-256 hashes of both outputs.

Usage:
  python -m src.predict --data ./data --out predictions.csv
  python -m src.predict --data ./data --version v1_2026-09-01 --out predictions.csv
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import pathlib
import sys

from src.load import load_telemetry
from src.serialization import hash_predictions_file, serialize_predictions_canonical
from src.train import (
    MODELS_DIR,
    load_model_artifact,
    score_all_weeks,
)

logger = logging.getLogger(__name__)

# ─── Prediction ────────────────────────────────────────────────────────────────


def predict(
    data_dir: pathlib.Path,
    out_path: pathlib.Path,
    version_id: str | None = None,
    models_dir: pathlib.Path = MODELS_DIR,
) -> pathlib.Path:
    """
    Load a model version and produce a valid predictions.csv.

    Steps:
      1. Load model artifact (ACTIVE if version_id is None)
      2. Load telemetry
      3. Score all 8 weeks using parameters from the artifact
      4. Write 120-row predictions.csv in the exact format validate_submission.py expects
      5. Return the output path

    The output is deterministic: same version + same data → same CSV bytes.
    """
    artifact = load_model_artifact(version_id, models_dir)
    params = artifact["parameters"]

    # Derive scored weeks from the artifact or use the standard 8-week window.
    scored_weeks = [
        dt.date.fromisoformat(w)
        for w in artifact.get(
            "scored_weeks",
            [(dt.date(2026, 2, 2) + dt.timedelta(days=7 * i)).isoformat() for i in range(8)],
        )
    ]

    logger.info("Using model version: %s (%s)", artifact["version_id"], artifact["model_type"])
    logger.info(
        "Parameters: sigma=%s, baseline_days=%s", params["sigma"], params["baseline_days"]
    )

    telemetry = load_telemetry(data_dir)
    logger.info("Loaded %s telemetry rows.", f"{len(telemetry):,}")

    predictions = score_all_weeks(
        telemetry=telemetry,
        scored_weeks=scored_weeks,
        sigma=float(params["sigma"]),
        baseline_days=int(params["baseline_days"]),
        recent_days=int(params["recent_days"]),
    )

    # Write CSV using the canonical serialization — the same bytes that
    # _hash_predictions_canonical() hashes, ensuring the file on disk is
    # byte-for-byte consistent with the stored fixed_slice_prediction_hash.
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canonical_bytes = serialize_predictions_canonical(predictions)
    out_path.write_bytes(canonical_bytes)

    row_count = len(predictions)
    week_count = predictions["week_start"].nunique()
    file_hash = hash_predictions_file(out_path)
    logger.info("[OK] Wrote %s — %d rows over %d weeks", out_path, row_count, week_count)
    logger.info("  Output hash: %s", file_hash)

    return out_path


# ─── CLI entry point ──────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Produce a ranked predictions.csv using a versioned model artifact."
    )
    parser.add_argument(
        "--data",
        type=pathlib.Path,
        required=True,
        help="Path to the data directory.",
    )
    parser.add_argument(
        "--out",
        type=pathlib.Path,
        default=pathlib.Path("predictions.csv"),
        help="Output path for predictions.csv (default: ./predictions.csv).",
    )
    parser.add_argument(
        "--version",
        type=str,
        default=None,
        help="Model version ID (e.g. v1_2026-09-01). Defaults to the ACTIVE version.",
    )
    parser.add_argument(
        "--models-dir",
        type=pathlib.Path,
        default=MODELS_DIR,
        help="Path to the model registry directory (default: ./models).",
    )
    args = parser.parse_args(argv)

    predict(
        data_dir=args.data,
        out_path=args.out,
        version_id=args.version,
        models_dir=args.models_dir,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

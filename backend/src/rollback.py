"""
Model registry management and rollback controller.

The rollback design makes the live-session demo work in under 60 seconds:
  1. Rollback = pointer file flip (models/ACTIVE) — instant, no recompute.
  2. verify   = re-run predict on a fixed slice, compare SHA-256 hash.
               Gives an objective "it worked" signal without external ground truth.
  3. Nothing in the pipeline auto-triggers training. Train/promote are always
     explicit CLI commands. Nothing can accidentally kick off a long job during
     the live session.

Subcommands:
  python -m src.rollback list
  python -m src.rollback current
  python -m src.rollback to <version_id> --reason "..."
  python -m src.rollback verify [--version <version_id>]

Audit trail:
  Every `to` command appends one JSON line to models/rollback_log.jsonl:
  {"timestamp": "...", "from_version": "...", "to_version": "...", "reason": "..."}
  The file is append-only. It is never truncated or modified.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import pathlib
import sys

from src.load import load_telemetry
from src.serialization import hash_predictions_canonical
from src.train import (
    MODELS_DIR,
    VERIFY_SLICE_DATE,
    load_model_artifact,
    score_all_weeks,
)

logger = logging.getLogger(__name__)

# ─── Registry inspection ──────────────────────────────────────────────────────


def get_current_active(models_dir: pathlib.Path = MODELS_DIR) -> str | None:
    """Return the current ACTIVE version ID, or None if ACTIVE does not exist."""
    active_path = models_dir / "ACTIVE"
    if not active_path.exists():
        return None
    return active_path.read_text(encoding="utf-8").strip()


def list_versions(models_dir: pathlib.Path = MODELS_DIR) -> list[dict]:  # type: ignore[type-arg]
    """
    List all model versions in the registry.
    Returns a list of dicts with: version_id, trained_at, model_type, is_active.
    """
    active = get_current_active(models_dir)
    versions = []

    for artifact_path in sorted(models_dir.glob("*.json")):
        try:
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            versions.append(
                {
                    "version_id": artifact.get("version_id", artifact_path.stem),
                    "trained_at": artifact.get("trained_at", "unknown"),
                    "model_type": artifact.get("model_type", "unknown"),
                    "is_active": artifact.get("version_id") == active,
                    "parameters": artifact.get("parameters", {}),
                    "training_data_hash": artifact.get("training_data_hash", ""),
                }
            )
        except (json.JSONDecodeError, KeyError):
            versions.append(
                {
                    "version_id": artifact_path.stem,
                    "trained_at": "unknown",
                    "model_type": "unknown",
                    "is_active": artifact_path.stem == active,
                    "parameters": {},
                    "training_data_hash": "",
                }
            )

    return versions


def get_rollback_log(models_dir: pathlib.Path = MODELS_DIR) -> list[dict]:  # type: ignore[type-arg]
    """Read the append-only rollback audit log."""
    log_path = models_dir / "rollback_log.jsonl"
    if not log_path.exists():
        return []
    entries = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


# ─── Rollback execution ───────────────────────────────────────────────────────


def rollback_to(
    to_version: str,
    reason: str,
    models_dir: pathlib.Path = MODELS_DIR,
) -> None:
    """
    Roll back to a specific model version.

    Safety checks:
      - The target version artifact must exist (fails loud if not).
      - Appends an audit entry to rollback_log.jsonl BEFORE updating ACTIVE
        (so the log is consistent even if the write crashes mid-way).

    WHY we check artifact existence:
      A typo in the version name would silently point ACTIVE at a non-existent
      file. The predict step would then fail with a confusing "not found" error
      instead of a clear rollback error at the moment of the rollback.
    """
    artifact_path = models_dir / f"{to_version}.json"
    if not artifact_path.exists():
        available = [p.stem for p in sorted(models_dir.glob("*.json"))]
        raise FileNotFoundError(
            f"Version '{to_version}' not found in {models_dir}.\n"
            f"Available versions: {available}"
        )

    from_version = get_current_active(models_dir) or "none"

    # Write audit log BEFORE updating ACTIVE.
    log_entry = {
        "timestamp": dt.datetime.now(dt.UTC).isoformat(),
        "from_version": from_version,
        "to_version": to_version,
        "reason": reason,
    }
    log_path = models_dir / "rollback_log.jsonl"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")

    # Atomically update ACTIVE pointer via temporary file replace.
    active_path = models_dir / "ACTIVE"
    tmp_path = models_dir / f".ACTIVE.{dt.datetime.now(dt.UTC).timestamp()}.tmp"
    tmp_path.write_text(to_version, encoding="utf-8")
    tmp_path.replace(active_path)

    logger.info("[OK] Rolled back: %s -> %s", from_version, to_version)
    logger.info("  Reason: %s", reason)
    logger.info("  Logged to %s", log_path)


# ─── Verify ───────────────────────────────────────────────────────────────────


def verify(
    data_dir: pathlib.Path,
    version_id: str | None = None,
    models_dir: pathlib.Path = MODELS_DIR,
) -> bool:
    """
    Verify that the active (or specified) model version produces the expected output.

    Method:
      1. Load the model artifact and its stored fixed_slice_prediction_hash.
      2. Re-run predictions for the fixed verify slice date.
      3. Compute SHA-256 of the output.
      4. Compare to the stored hash.
      5. Return True if they match (PASS), False if they differ (FAIL).

    WHY this is a strong proof:
      SHA-256 collision probability is negligible. If the hashes match, the
      model version is producing byte-identical output to when it was trained.
      This is objective "it worked" evidence that doesn't require external
      ground truth or manual inspection of 15 rows.
    """
    artifact = load_model_artifact(version_id, models_dir)
    expected_hash = artifact.get("fixed_slice_prediction_hash")
    ver = artifact["version_id"]

    if not expected_hash:
        logger.warning("No fixed_slice_prediction_hash stored in %s. Cannot verify.", ver)
        return False

    params = artifact["parameters"]

    logger.info("Verifying model version: %s", ver)
    logger.info("Fixed slice date: %s", VERIFY_SLICE_DATE)
    logger.info("Expected hash: %s", expected_hash)

    telemetry = load_telemetry(data_dir)

    verify_weeks = [VERIFY_SLICE_DATE]
    predictions = score_all_weeks(
        telemetry=telemetry,
        scored_weeks=verify_weeks,
        sigma=float(params["sigma"]),
        baseline_days=int(params["baseline_days"]),
        recent_days=int(params["recent_days"]),
    )

    # Use the canonical hash path — same function as training and predict.py.
    # This is what makes training hash == rollback verify hash.
    computed_hash = hash_predictions_canonical(predictions)
    logger.info("Computed hash: %s", computed_hash)

    if computed_hash == expected_hash:
        logger.info("[OK] PASS -- %s produces byte-identical output to training time.", ver)
        return True
    else:
        logger.warning("[FAIL] Hash mismatch. Active version does not reproduce expected output.")
        return False


# ─── CLI entry point ──────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage the model registry and execute rollbacks.")
    parser.add_argument("--models-dir", type=pathlib.Path, default=MODELS_DIR)
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list
    subparsers.add_parser("list", help="List all versions in the registry.")

    # current
    subparsers.add_parser("current", help="Print the current ACTIVE version.")

    # to
    to_parser = subparsers.add_parser("to", help="Roll back to a specific version.")
    to_parser.add_argument("version_id", type=str, help="Target version ID.")
    to_parser.add_argument(
        "--reason",
        type=str,
        required=True,
        help="Reason for the rollback (logged to rollback_log.jsonl).",
    )

    # verify
    verify_parser = subparsers.add_parser(
        "verify", help="Verify the active version produces expected output."
    )
    verify_parser.add_argument(
        "--data",
        type=pathlib.Path,
        required=True,
        help="Path to the data directory.",
    )
    verify_parser.add_argument(
        "--version",
        type=str,
        default=None,
        help="Version to verify (default: ACTIVE).",
    )

    args = parser.parse_args(argv)

    if args.command == "list":
        versions = list_versions(args.models_dir)
        if not versions:
            print("No model versions found in registry.")
            return 0
        for v in versions:
            active_marker = " [ACTIVE]" if v["is_active"] else ""
            print(
                f"  {v['version_id']}{active_marker}  |  "
                f"trained: {v['trained_at'][:10]}  |  type: {v['model_type']}"
            )

    elif args.command == "current":
        current = get_current_active(args.models_dir)
        if current:
            print(current)
        else:
            print("No ACTIVE version set.")
            return 1

    elif args.command == "to":
        rollback_to(
            to_version=args.version_id,
            reason=args.reason,
            models_dir=args.models_dir,
        )

    elif args.command == "verify":
        passed = verify(
            data_dir=args.data,
            version_id=args.version,
            models_dir=args.models_dir,
        )
        return 0 if passed else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

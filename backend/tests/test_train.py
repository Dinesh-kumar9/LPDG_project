"""
Unit tests for the model training artifact produced by src/train.py.

Coverage targets (per TASK 6 requirements):
  (a) The model JSON produced by train.py contains all required keys.
  (b) training_data_hash matches an independently recomputed hash of the
      same input data.
  (c) fixed_slice_prediction_hash matches re-running predict on that fixed
      slice using the freshly trained version.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import tempfile

import pytest

from src.load import load_telemetry
from src.train import (
    METRICS,
    VERIFY_SLICE_DATE,
    _hash_dataframe,
    _hash_predictions_csv,
    score_all_weeks,
    write_model_artifact,
)

# ─── Required artifact keys ───────────────────────────────────────────────────

REQUIRED_ARTIFACT_KEYS = {
    "version_id",
    "model_type",
    "trained_at",
    "training_window",
    "parameters",
    "scored_weeks",
    "training_data_hash",
    "fixed_slice_prediction_hash",
    "fixed_slice_date",
    "known_gateway_ids",
    "known_gateway_count",
    "promoted",
}

REQUIRED_PARAMETER_KEYS = {
    "sigma",
    "baseline_days",
    "recent_days",
    "metrics",
    "visits_per_week",
}


# ─── Test (a): required keys ──────────────────────────────────────────────────


def test_artifact_contains_required_keys(
    real_data_dir: pathlib.Path,
    temp_models_dir: pathlib.Path,
) -> None:
    """
    (a) The model JSON produced by train.py contains ALL required top-level
    keys and nested parameter keys.
    """
    telemetry = load_telemetry(real_data_dir)
    artifact_path = write_model_artifact(
        telemetry=telemetry,
        models_dir=temp_models_dir,
        version_name="test_keys",
        sigma=3.0,
        promote=False,
    )

    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    missing_top = REQUIRED_ARTIFACT_KEYS - artifact.keys()
    assert not missing_top, f"Artifact is missing top-level keys: {missing_top}"

    missing_params = REQUIRED_PARAMETER_KEYS - artifact["parameters"].keys()
    assert not missing_params, f"parameters dict is missing keys: {missing_params}"


def test_artifact_value_types(
    real_data_dir: pathlib.Path,
    temp_models_dir: pathlib.Path,
) -> None:
    """Verify critical field types are correct so downstream consumers do not crash."""
    telemetry = load_telemetry(real_data_dir)
    artifact_path = write_model_artifact(
        telemetry=telemetry,
        models_dir=temp_models_dir,
        version_name="test_types",
        sigma=3.0,
        promote=False,
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert isinstance(artifact["version_id"], str)
    assert isinstance(artifact["known_gateway_ids"], list)
    assert isinstance(artifact["known_gateway_count"], int)
    assert artifact["known_gateway_count"] == len(artifact["known_gateway_ids"])
    assert isinstance(artifact["parameters"]["sigma"], float)
    assert isinstance(artifact["parameters"]["baseline_days"], int)
    assert isinstance(artifact["parameters"]["recent_days"], int)
    assert isinstance(artifact["parameters"]["metrics"], list)

    # training_window must parse as ISO dates
    tw = artifact["training_window"]
    dt.date.fromisoformat(tw["start"])
    dt.date.fromisoformat(tw["end"])


def test_artifact_scored_weeks_covers_8_weeks(
    real_data_dir: pathlib.Path,
    temp_models_dir: pathlib.Path,
) -> None:
    """scored_weeks must cover exactly 8 weeks (the graded submission window)."""
    telemetry = load_telemetry(real_data_dir)
    artifact_path = write_model_artifact(
        telemetry=telemetry,
        models_dir=temp_models_dir,
        version_name="test_weeks",
        sigma=3.0,
        promote=False,
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert (
        len(artifact["scored_weeks"]) == 8
    ), f"Expected 8 scored weeks, got {len(artifact['scored_weeks'])}"
    # First week must be 2026-02-02
    assert artifact["scored_weeks"][0] == "2026-02-02"


# ─── Test (b): training_data_hash ─────────────────────────────────────────────


def test_training_data_hash_matches_independent_recompute(
    real_data_dir: pathlib.Path,
    temp_models_dir: pathlib.Path,
) -> None:
    """
    (b) training_data_hash stored in the artifact must match the SHA-256 of
    the canonical CSV representation of the same telemetry DataFrame, computed
    independently here.
    """
    telemetry = load_telemetry(real_data_dir)

    # Independently recompute the hash the same way train.py does.
    independent_hash = _hash_dataframe(
        telemetry[["gateway_id", "ts"] + METRICS].sort_values(["gateway_id", "ts"])
    )

    artifact_path = write_model_artifact(
        telemetry=telemetry,
        models_dir=temp_models_dir,
        version_name="test_hash",
        sigma=3.0,
        promote=False,
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact["training_data_hash"] == independent_hash, (
        f"training_data_hash mismatch:\n"
        f"  stored:      {artifact['training_data_hash']}\n"
        f"  recomputed:  {independent_hash}"
    )


def test_training_data_hash_is_sha256_prefixed(
    real_data_dir: pathlib.Path,
    temp_models_dir: pathlib.Path,
) -> None:
    """Hash must be prefixed sha256: and be 71 chars total (7 prefix + 64 hex)."""
    telemetry = load_telemetry(real_data_dir)
    artifact_path = write_model_artifact(
        telemetry=telemetry,
        models_dir=temp_models_dir,
        version_name="test_hash_fmt",
        sigma=3.0,
        promote=False,
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    h = artifact["training_data_hash"]
    assert h.startswith("sha256:"), f"Hash does not start with sha256: {h}"
    assert len(h) == 71, f"Expected 71 chars (sha256:<64-hex>), got {len(h)}: {h}"


def test_training_data_hash_stable_across_two_loads(
    real_data_dir: pathlib.Path,
    temp_models_dir: pathlib.Path,
) -> None:
    """
    Loading the same data twice produces identical training_data_hash values.
    Confirms load.py and hashing are deterministic.
    """
    telemetry_a = load_telemetry(real_data_dir)
    artifact_a = write_model_artifact(
        telemetry=telemetry_a,
        models_dir=temp_models_dir,
        version_name="test_hash_stable_a",
        sigma=3.0,
    )

    telemetry_b = load_telemetry(real_data_dir)
    artifact_b = write_model_artifact(
        telemetry=telemetry_b,
        models_dir=temp_models_dir,
        version_name="test_hash_stable_b",
        sigma=3.0,
    )

    a = json.loads(artifact_a.read_text(encoding="utf-8"))
    b = json.loads(artifact_b.read_text(encoding="utf-8"))
    assert a["training_data_hash"] == b["training_data_hash"]


# ─── Test (c): fixed_slice_prediction_hash ────────────────────────────────────


def test_fixed_slice_hash_matches_rerun(
    real_data_dir: pathlib.Path,
    temp_models_dir: pathlib.Path,
) -> None:
    """
    (c) fixed_slice_prediction_hash stored in the artifact must equal the hash
    produced by independently re-running score_all_weeks on VERIFY_SLICE_DATE
    with the same parameters. This is exactly what rollback verify performs.
    """
    telemetry = load_telemetry(real_data_dir)

    artifact_path = write_model_artifact(
        telemetry=telemetry,
        models_dir=temp_models_dir,
        version_name="test_slice",
        sigma=3.0,
        promote=False,
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    stored_hash = artifact["fixed_slice_prediction_hash"]
    params = artifact["parameters"]

    # Independently re-run score_all_weeks on the same fixed verify slice.
    predictions = score_all_weeks(
        telemetry=telemetry,
        scored_weeks=[VERIFY_SLICE_DATE],
        sigma=float(params["sigma"]),
        baseline_days=int(params["baseline_days"]),
        recent_days=int(params["recent_days"]),
    )

    with tempfile.NamedTemporaryFile(
        suffix=".csv", delete=False, mode="w", encoding="utf-8"
    ) as tmp:
        tmp_path = pathlib.Path(tmp.name)
        predictions.to_csv(tmp_path, index=False, float_format="%.1f")

    recomputed_hash = _hash_predictions_csv(tmp_path)
    tmp_path.unlink()

    assert recomputed_hash == stored_hash, (
        f"fixed_slice_prediction_hash mismatch:\n"
        f"  stored:      {stored_hash}\n"
        f"  recomputed:  {recomputed_hash}"
    )


def test_fixed_slice_date_is_stored_correctly(
    real_data_dir: pathlib.Path,
    temp_models_dir: pathlib.Path,
) -> None:
    """
    fixed_slice_date in the artifact must equal VERIFY_SLICE_DATE. If this
    drifts, rollback verify will compare against the wrong slice.
    """
    telemetry = load_telemetry(real_data_dir)
    artifact_path = write_model_artifact(
        telemetry=telemetry,
        models_dir=temp_models_dir,
        version_name="test_slice_date",
        sigma=3.0,
        promote=False,
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["fixed_slice_date"] == VERIFY_SLICE_DATE.isoformat(), (
        f"fixed_slice_date stored as {artifact['fixed_slice_date']!r}, "
        f"expected {VERIFY_SLICE_DATE.isoformat()!r}"
    )


def test_sigma999_artifact_still_has_required_keys(
    real_data_dir: pathlib.Path,
    temp_models_dir: pathlib.Path,
) -> None:
    """
    Even a deliberately broken model (sigma=999) must produce a structurally
    valid artifact — train.py must never write a partial JSON.
    """
    telemetry = load_telemetry(real_data_dir)
    artifact_path = write_model_artifact(
        telemetry=telemetry,
        models_dir=temp_models_dir,
        version_name="test_broken",
        sigma=999.0,
        promote=False,
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    missing = REQUIRED_ARTIFACT_KEYS - artifact.keys()
    assert not missing, f"Broken model artifact missing keys: {missing}"
    assert artifact["parameters"]["sigma"] == 999.0


def test_write_model_artifact_atomic_no_duplicate(
    real_data_dir: pathlib.Path,
    temp_models_dir: pathlib.Path,
) -> None:
    """
    Writing the same version name twice must raise FileExistsError — the
    registry must never silently overwrite an existing artifact.
    """
    telemetry = load_telemetry(real_data_dir)
    write_model_artifact(
        telemetry=telemetry,
        models_dir=temp_models_dir,
        version_name="test_dup",
        sigma=3.0,
    )
    with pytest.raises(FileExistsError):
        write_model_artifact(
            telemetry=telemetry,
            models_dir=temp_models_dir,
            version_name="test_dup",
            sigma=3.0,
        )

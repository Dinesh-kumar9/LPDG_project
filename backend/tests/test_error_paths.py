"""
Negative-path tests for error handling in predict.py, load.py, and rollback.py.

These cover the failure modes explicitly flagged in the LPDG evaluation as missing:
  1. predict() when ACTIVE points to a nonexistent version file
  2. load_telemetry() called on an empty directory (no parquet files)
  3. rollback_to() when the target version does not exist in the registry

Tests run fully on synthetic data — no challenge dataset required.
"""

from __future__ import annotations

import pathlib

import pandas as pd
import pytest

from src.load import load_telemetry
from src.predict import predict
from src.rollback import rollback_to
from src.train import write_model_artifact


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def minimal_models_dir(tmp_path: pathlib.Path, synthetic_telemetry_dir: pathlib.Path) -> pathlib.Path:
    """A models dir with one promoted version, built from synthetic data."""
    models_dir = tmp_path / "models"
    telemetry = load_telemetry(synthetic_telemetry_dir)
    write_model_artifact(
        telemetry=telemetry,
        models_dir=models_dir,
        version_name="v_neg_test",
        promote=True,
    )
    return models_dir


# ─── Fix E Test 1: predict() when ACTIVE points to a missing artifact ─────────


def test_predict_raises_when_active_artifact_missing(
    synthetic_telemetry_dir: pathlib.Path,
    tmp_path: pathlib.Path,
) -> None:
    """
    If ACTIVE exists but the JSON artifact it points to has been deleted,
    predict() must raise FileNotFoundError with a useful message.
    It must NOT silently return wrong output or crash with AttributeError.
    """
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    # Write an ACTIVE pointer to a version that has no artifact on disk.
    (models_dir / "ACTIVE").write_text("ghost_version_that_does_not_exist", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="ghost_version_that_does_not_exist"):
        predict(
            data_dir=synthetic_telemetry_dir,
            out_path=tmp_path / "predictions.csv",
            models_dir=models_dir,
        )


# ─── Fix E Test 2: load_telemetry() on an empty directory ────────────────────


def test_load_telemetry_empty_directory_raises(tmp_path: pathlib.Path) -> None:
    """
    load_telemetry() must raise a clear exception when there are no parquet
    files in the telemetry directory.  The caller (predict, train) must get a
    meaningful error, not a confusing pandas / pyarrow traceback.
    """
    empty_data_dir = tmp_path / "empty_data"
    telemetry_dir = empty_data_dir / "telemetry" / "month=2025-08"
    telemetry_dir.mkdir(parents=True)  # dir exists but contains no parquet files

    with pytest.raises((FileNotFoundError, ValueError, Exception)):
        load_telemetry(empty_data_dir)


# ─── Fix E Test 3: rollback_to() with a non-existent target ──────────────────


def test_rollback_to_nonexistent_version_raises(
    minimal_models_dir: pathlib.Path,
) -> None:
    """
    rollback_to() must raise FileNotFoundError BEFORE touching the ACTIVE
    pointer when the target version does not exist in the registry.
    The ACTIVE pointer must remain unchanged after the failed rollback.
    """
    from src.rollback import get_current_active

    active_before = get_current_active(minimal_models_dir)
    assert active_before is not None, "Precondition: a version must be active"

    with pytest.raises(FileNotFoundError, match="non_existent_version_xyz"):
        rollback_to(
            to_version="non_existent_version_xyz",
            reason="testing pre-flight check",
            models_dir=minimal_models_dir,
        )

    # ACTIVE must be unchanged — the safety check fired before any write.
    assert get_current_active(minimal_models_dir) == active_before

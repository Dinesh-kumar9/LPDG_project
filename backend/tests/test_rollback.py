"""
Unit tests for model registry and rollback mechanism (src/rollback.py).
"""

from __future__ import annotations

import pathlib

import pytest

from src.load import load_telemetry
from src.rollback import (
    get_current_active,
    get_rollback_log,
    list_versions,
    rollback_to,
    verify,
)
from src.train import write_model_artifact


def test_rollback_lifecycle(real_data_dir: pathlib.Path, temp_models_dir: pathlib.Path):
    telemetry = load_telemetry(real_data_dir)

    # 1. Train v1 and promote
    p1 = write_model_artifact(
        telemetry=telemetry,
        models_dir=temp_models_dir,
        version_name="v1_good",
        sigma=3.0,
        promote=True,
    )
    v1_id = p1.stem
    assert get_current_active(temp_models_dir) == v1_id

    # 2. Train v2 (bad / experimental) and promote
    p2 = write_model_artifact(
        telemetry=telemetry,
        models_dir=temp_models_dir,
        version_name="v2_broken",
        sigma=999.0,
        promote=True,
    )
    v2_id = p2.stem
    assert get_current_active(temp_models_dir) == v2_id

    # 3. Verify registry lists both versions
    versions = list_versions(temp_models_dir)
    assert len(versions) == 2
    v2_entry = next(v for v in versions if v["version_id"] == v2_id)
    assert v2_entry["is_active"] is True

    # 4. Rollback to v1
    reason_msg = "v2 regressed: sigma 999 produces degenerate rankings"
    rollback_to(to_version=v1_id, reason=reason_msg, models_dir=temp_models_dir)
    assert get_current_active(temp_models_dir) == v1_id

    # 5. Check audit log
    logs = get_rollback_log(temp_models_dir)
    assert len(logs) == 1
    assert logs[0]["from_version"] == v2_id
    assert logs[0]["to_version"] == v1_id
    assert logs[0]["reason"] == reason_msg

    # 6. Verify v1 hash match
    assert verify(data_dir=real_data_dir, version_id=v1_id, models_dir=temp_models_dir) is True


def test_rollback_to_invalid_version_raises(temp_models_dir: pathlib.Path):
    with pytest.raises(FileNotFoundError):
        rollback_to(
            "non_existent_version", reason="testing error handling", models_dir=temp_models_dir
        )

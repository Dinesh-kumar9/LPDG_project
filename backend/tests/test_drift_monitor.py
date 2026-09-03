"""
Unit tests for drift monitor (src/drift_monitor.py).
"""

from __future__ import annotations

import pathlib
import pytest

from src.load import load_telemetry
from src.train import write_model_artifact
from src.drift_monitor import run_drift_check, count_consecutive_flags


def test_drift_monitor_clean_data(
    real_data_dir: pathlib.Path,
    temp_models_dir: pathlib.Path,
    temp_reports_dir: pathlib.Path,
):
    telemetry = load_telemetry(real_data_dir)
    write_model_artifact(
        telemetry=telemetry,
        models_dir=temp_models_dir,
        version_name="v1_ref",
        promote=True,
    )

    report = run_drift_check(
        data_dir=real_data_dir,
        reports_dir=temp_reports_dir,
        models_dir=temp_models_dir,
    )

    assert report.drift_flagged is False
    assert report.missing_columns == []
    assert report.new_columns == []
    assert count_consecutive_flags(temp_reports_dir) == 0

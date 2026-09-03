"""
Pytest configuration and fixtures.
"""

from __future__ import annotations

import pathlib
import sys
import pytest

# Ensure backend root is on sys.path
BACKEND_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Project root containing original OneDrive test data
PROJECT_ROOT = BACKEND_ROOT.parent.parent
SAMPLE_DATA_DIR = PROJECT_ROOT / "OneDrive_1_8-30-2026" / "03-challenge-data" / "data"


@pytest.fixture
def real_data_dir() -> pathlib.Path:
    if SAMPLE_DATA_DIR.exists():
        return SAMPLE_DATA_DIR
    pytest.skip(f"Data directory not found at {SAMPLE_DATA_DIR}")


@pytest.fixture
def temp_models_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    return models_dir


@pytest.fixture
def temp_reports_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    reports_dir = tmp_path / "drift_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    return reports_dir

"""
Pytest configuration and fixtures.
"""

from __future__ import annotations

import pathlib
import sys

import numpy as np
import pandas as pd
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


@pytest.fixture
def synthetic_telemetry_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    """Create a portable, schema-valid telemetry batch for drift tests.

    This fixture is deliberately generated at test time: no challenge data is
    committed, while CI still exercises the real parquet ingestion path.
    """
    data_dir = tmp_path / "data"
    telemetry_dir = data_dir / "telemetry" / "month=2025-08"
    telemetry_dir.mkdir(parents=True)

    timestamps = pd.date_range("2025-08-01", "2026-03-23", freq="D", tz="UTC")
    gateway_ids = [f"0A000000{index:04X}" for index in range(15)]
    index = pd.MultiIndex.from_product([gateway_ids, timestamps], names=["gateway_id", "ts_utc"])
    frame = index.to_frame(index=False)
    day_offset = np.arange(len(frame)) % len(timestamps)
    gateway_offset = np.repeat(np.arange(len(gateway_ids)), len(timestamps))

    frame["offline_duration_sec"] = 10.0 + (day_offset % 5) + gateway_offset
    frame["disconnection_cnt"] = 1.0 + (day_offset % 3)
    frame["reboot_cnt"] = (day_offset % 2).astype(float)
    for column in [
        "rssi_good",
        "rssi_normal",
        "rssi_bad",
        "rscp_rsrp_good",
        "rscp_rsrp_normal",
        "rscp_rsrp_bad",
        "network_2g",
        "network_3g",
        "network_4g",
        "rx_nr_pkts",
        "rx_crc_bad",
        "reboot_importance",
        "no_conn_importance",
        "avg_load1",
        "avg_memfree",
    ]:
        frame[column] = 1.0

    frame.to_parquet(telemetry_dir / "part-0.parquet", index=False)
    return data_dir

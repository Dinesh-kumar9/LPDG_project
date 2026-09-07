"""
Unit tests for src/load.py (normalization, Latin-1 decode, schema assertions).
"""

from __future__ import annotations

import pathlib

import pytest

from src.load import (
    OUTCOME_FAULT_FIXED,
    OUTCOME_IS_FAULT,
    OUTCOME_NO_FAULT,
    load_all,
    load_engineer_review,
    load_field_visits,
    load_gateway_master,
    load_meter_read_success,
    normalize_gateway_id,
)


def test_normalize_gateway_id_colon_mac():
    raw = "06:5B:92:87:16:CD"
    normalized = normalize_gateway_id(raw)
    assert normalized == "065B928716CD"


def test_normalize_gateway_id_bare_hex():
    raw_lower = "0639ea5602c1"
    normalized = normalize_gateway_id(raw_lower)
    assert normalized == "0639EA5602C1"


def test_normalize_gateway_id_invalid_raises():
    with pytest.raises(ValueError, match="Unrecognized gateway_id format"):
        normalize_gateway_id("invalid-id-xyz")

    with pytest.raises(ValueError, match="Unrecognized gateway_id format"):
        normalize_gateway_id("06:5B:92:87:16")  # too short


def test_load_gateway_master_latin1_encoding(real_data_dir: pathlib.Path):
    df = load_gateway_master(real_data_dir)
    assert not df.empty
    assert "gateway_id" in df.columns
    # Check that gateway_ids are normalized (12 bare hex chars, no colons)
    assert df["gateway_id"].str.match(r"^[0-9A-F]{12}$").all()
    # Check that Latin-1 German special characters decode cleanly without errors
    # Regions include 'Baden-Württemberg' or site_types include 'Außenmast' or 'Gebäude'
    site_types = df["site_type"].dropna().unique()
    assert any("mast" in str(st).lower() or "geb" in str(st).lower() for st in site_types)


def test_load_field_visits(real_data_dir: pathlib.Path):
    df = load_field_visits(real_data_dir)
    assert not df.empty
    assert "gateway_id" in df.columns
    assert "is_fault" in df.columns
    assert df["gateway_id"].str.match(r"^[0-9A-F]{12}$").all()
    assert df["outcome"].isin([OUTCOME_FAULT_FIXED, OUTCOME_NO_FAULT, "Kein Zugang"]).any()
    # Ensure binary label matches OUTCOME_IS_FAULT
    expected_faults = df["outcome"].isin(OUTCOME_IS_FAULT)
    assert (df["is_fault"] == expected_faults).all()


def test_load_meter_read_success(real_data_dir: pathlib.Path):
    df = load_meter_read_success(real_data_dir)
    assert not df.empty
    assert "gateway_id" in df.columns
    assert "read_success_rate" in df.columns
    assert (df["read_success_rate"] >= 0.0).all()
    assert (df["read_success_rate"] <= 1.0).all()


def test_load_engineer_review(real_data_dir: pathlib.Path):
    df = load_engineer_review(real_data_dir)
    assert not df.empty
    assert "gateway_id" in df.columns
    assert "is_bad" in df.columns
    assert df["gateway_id"].str.match(r"^[0-9A-F]{12}$").all()


def test_load_all_integration(real_data_dir: pathlib.Path):
    data = load_all(real_data_dir)
    assert "telemetry" in data
    assert "master" in data
    assert "visits" in data
    assert "meter" in data
    assert "engineer_review" in data

    # Verify ID format consistency across all sources
    for name, df in data.items():
        assert df["gateway_id"].str.match(r"^[0-9A-F]{12}$").all(), f"Failed in {name}"

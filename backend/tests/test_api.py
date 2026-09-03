"""
Unit and integration tests for FastAPI backend routes.
"""

from __future__ import annotations

import pathlib
import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.dependencies import get_settings, Settings
from src.load import load_telemetry
from src.train import write_model_artifact


@pytest.fixture
def client(real_data_dir: pathlib.Path, temp_models_dir: pathlib.Path, temp_reports_dir: pathlib.Path, tmp_path: pathlib.Path):
    pred_path = tmp_path / "predictions.csv"
    
    # Train and promote a test model version first
    telemetry = load_telemetry(real_data_dir)
    write_model_artifact(
        telemetry=telemetry,
        models_dir=temp_models_dir,
        version_name="v1_api_test",
        promote=True,
    )

    test_settings = Settings(
        data_dir=real_data_dir,
        models_dir=temp_models_dir,
        reports_dir=temp_reports_dir,
        predictions_path=pred_path,
    )

    app.dependency_overrides[get_settings] = lambda: test_settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_health_check(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "1.0.0"}


def test_get_registry_and_version_details(client: TestClient):
    res = client.get("/api/registry")
    assert res.status_code == 200
    data = res.json()
    assert data["active_version"] is not None
    assert len(data["versions"]) >= 1

    active_id = data["active_version"]
    res_details = client.get(f"/api/registry/versions/{active_id}")
    assert res_details.status_code == 200
    details = res_details.json()
    assert details["version_id"] == active_id
    assert details["is_active"] is True


def test_predictions_api(client: TestClient):
    res = client.get("/api/predictions")
    assert res.status_code == 200
    data = res.json()
    assert data["total_rows"] == 120
    assert len(data["available_weeks"]) == 8
    assert len(data["predictions"]) == 120

    # Filter by specific week
    week = data["available_weeks"][0]
    res_week = client.get(f"/api/predictions?week_start={week}")
    assert res_week.status_code == 200
    week_data = res_week.json()
    assert week_data["total_rows"] == 15

    # Download CSV
    res_csv = client.get("/api/predictions/download")
    assert res_csv.status_code == 200
    assert "text/csv" in res_csv.headers["content-type"]


def test_drift_api(client: TestClient):
    # Trigger drift check
    res_run = client.post("/api/drift/run")
    assert res_run.status_code == 200
    assert res_run.json()["status"] == "success"

    # Get status and history
    res_status = client.get("/api/drift/status")
    assert res_status.status_code == 200
    assert res_status.json()["total_reports"] >= 1

    res_history = client.get("/api/drift/history")
    assert res_history.status_code == 200
    assert res_history.json()["total"] >= 1


def test_rollback_api(client: TestClient, temp_models_dir: pathlib.Path, real_data_dir: pathlib.Path):
    # Train v2
    telemetry = load_telemetry(real_data_dir)
    p2 = write_model_artifact(
        telemetry=telemetry,
        models_dir=temp_models_dir,
        version_name="v2_for_rollback",
        promote=True,
    )
    v2_id = p2.stem

    # Get current registry
    res_reg = client.get("/api/registry")
    assert res_reg.json()["active_version"] == v2_id

    # Rollback to v1
    v1_id = [v["version_id"] for v in res_reg.json()["versions"] if v["version_id"] != v2_id][0]
    res_rb = client.post("/api/rollback/execute", json={"to_version": v1_id, "reason": "Testing API rollback"})
    assert res_rb.status_code == 200
    assert res_rb.json()["status"] == "success"

    # Verify rollback log
    res_log = client.get("/api/rollback/log")
    assert res_log.status_code == 200
    assert res_log.json()["total_entries"] >= 1

    # Verify hash via API
    res_verify = client.post(f"/api/rollback/verify?version_id={v1_id}")
    assert res_verify.status_code == 200
    assert res_verify.json()["verified"] is True

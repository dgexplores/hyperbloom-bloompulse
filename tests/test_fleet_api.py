"""Integration tests for fleet dashboard API endpoints."""
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app, asset_registry

client = TestClient(app)

# Clear registry before each test
@pytest.fixture(autouse=True)
def clear_registry():
    asset_registry._assets.clear()
    yield
    asset_registry._assets.clear()


def test_fleet_summary_empty():
    """Fleet summary returns empty list when no assets."""
    resp = client.get("/api/v1/fleet/summary")
    assert resp.status_code == 200
    assert resp.json() == []


def test_fleet_summary_with_assets():
    """Fleet summary includes all assets with last verdict data."""
    # Create two assets
    a1 = client.post("/api/v1/assets", json={"name": "BRG-05-A", "rpm": 1750}).json()
    a2 = client.post("/api/v1/assets", json={"name": "BRG-06-B", "rpm": 1800}).json()

    # Add some baseline data (simulating past verdicts)
    for asset_id in [a1["id"], a2["id"]]:
        client.post(f"/api/v1/assets/{asset_id}/baseline", json={"anomaly_index": 0.1})
        client.post(f"/api/v1/assets/{asset_id}/baseline", json={"anomaly_index": 0.2})
        client.post(f"/api/v1/assets/{asset_id}/baseline", json={"anomaly_index": 0.15})

    resp = client.get("/api/v1/fleet/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2

    for asset in data:
        assert "id" in asset
        assert "name" in asset
        assert "last_verdict" in asset
        assert "last_severity" in asset
        assert "last_timestamp" in asset
        assert "trend_sparkline" in asset
        assert isinstance(asset["trend_sparkline"], list)
        # Should have up to 30 trend points
        assert len(asset["trend_sparkline"]) <= 30


def test_fleet_summary_includes_verdict_data():
    """Fleet summary shows last verdict severity and timestamp."""
    a1 = client.post("/api/v1/assets", json={"name": "BRG-05-A"}).json()
    asset_id = a1["id"]

    # Simulate a verdict by updating baseline with anomaly_index
    client.post(f"/api/v1/assets/{asset_id}/baseline", json={"anomaly_index": 0.1})
    client.post(f"/api/v1/assets/{asset_id}/baseline", json={"anomaly_index": 0.82})  # critical

    resp = client.get("/api/v1/fleet/summary")
    data = resp.json()
    assert len(data) == 1
    asset = data[0]
    assert asset["last_severity"] in ["normal", "monitor", "alert", "critical"]
    assert asset["last_timestamp"] is not None


def test_fleet_filter_by_severity():
    """Filter fleet by severity level."""
    a1 = client.post("/api/v1/assets", json={"name": "BRG-05-A"}).json()
    a2 = client.post("/api/v1/assets", json={"name": "BRG-06-B"}).json()

    asset1_id = a1["id"]
    asset2_id = a2["id"]

    # Asset 1: critical
    for idx in [0.82, 0.85, 0.83]:
        client.post(f"/api/v1/assets/{asset1_id}/baseline", json={"anomaly_index": idx})
    # Asset 2: normal
    for idx in [0.1, 0.15, 0.12]:
        client.post(f"/api/v1/assets/{asset2_id}/baseline", json={"anomaly_index": idx})

    # Filter critical
    resp = client.get("/api/v1/fleet/filter?severity=critical")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "BRG-05-A"

    # Filter normal
    resp = client.get("/api/v1/fleet/filter?severity=normal")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "BRG-06-B"


def test_fleet_filter_pagination():
    """Fleet filter supports limit parameter."""
    for i in range(5):
        client.post("/api/v1/assets", json={"name": f"BRG-{i:02d}"})

    resp = client.get("/api/v1/fleet/filter?limit=2")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


def test_fleet_filter_invalid_severity():
    """Invalid severity returns 422 (FastAPI validation error)."""
    resp = client.get("/api/v1/fleet/filter?severity=invalid")
    assert resp.status_code == 422


def test_fleet_sparkline_capped_at_30():
    """Trend sparkline capped at 30 points."""
    a1 = client.post("/api/v1/assets", json={"name": "BRG-05-A"}).json()
    asset_id = a1["id"]

    # Add 35 trend points
    for i in range(35):
        client.post(f"/api/v1/assets/{asset_id}/baseline", json={"anomaly_index": i * 0.01})

    resp = client.get("/api/v1/fleet/summary")
    data = resp.json()
    asset = data[0]
    # Should be capped at 30
    assert len(asset["trend_sparkline"]) == 30
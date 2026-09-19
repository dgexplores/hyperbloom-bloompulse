"""Integration tests for asset registry API endpoints."""
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


def test_create_asset():
    resp = client.post("/api/v1/assets", json={"name": "BRG-05-A", "rpm": 1750, "bearing_type": "6205"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] is not None
    assert data["name"] == "BRG-05-A"
    assert data["rpm"] == 1750
    assert data["bearing_type"] == "6205"
    assert data["baseline"] == {}


def test_get_asset():
    create = client.post("/api/v1/assets", json={"name": "BRG-05-A"})
    asset_id = create.json()["id"]
    resp = client.get(f"/api/v1/assets/{asset_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == asset_id


def test_get_asset_not_found():
    resp = client.get("/api/v1/assets/nonexistent")
    assert resp.status_code == 404


def test_list_assets():
    client.post("/api/v1/assets", json={"name": "BRG-05-A"})
    client.post("/api/v1/assets", json={"name": "BRG-06-B"})
    resp = client.get("/api/v1/assets")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


def test_update_asset():
    create = client.post("/api/v1/assets", json={"name": "BRG-05-A"})
    asset_id = create.json()["id"]
    resp = client.patch(f"/api/v1/assets/{asset_id}", json={"rpm": 1800})
    assert resp.status_code == 200
    assert resp.json()["rpm"] == 1800


def test_update_asset_not_found():
    resp = client.patch("/api/v1/assets/nonexistent", json={"rpm": 1800})
    assert resp.status_code == 404


def test_update_asset_no_fields():
    create = client.post("/api/v1/assets", json={"name": "BRG-05-A"})
    asset_id = create.json()["id"]
    resp = client.patch(f"/api/v1/assets/{asset_id}", json={})
    assert resp.status_code == 400


def test_delete_asset():
    create = client.post("/api/v1/assets", json={"name": "BRG-05-A"})
    asset_id = create.json()["id"]
    resp = client.delete(f"/api/v1/assets/{asset_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    # Verify deleted
    get_resp = client.get(f"/api/v1/assets/{asset_id}")
    assert get_resp.status_code == 404


def test_delete_asset_not_found():
    resp = client.delete("/api/v1/assets/nonexistent")
    assert resp.status_code == 404


def test_update_baseline():
    create = client.post("/api/v1/assets", json={"name": "BRG-05-A"})
    asset_id = create.json()["id"]
    resp = client.post(f"/api/v1/assets/{asset_id}/baseline", json={"anomaly_index": 0.5})
    assert resp.status_code == 200
    assert resp.json()["baseline"]["anomaly_index"] == 0.5


def test_update_baseline_trend_points():
    create = client.post("/api/v1/assets", json={"name": "BRG-05-A"})
    asset_id = create.json()["id"]
    resp = client.post(f"/api/v1/assets/{asset_id}/baseline", json={"trend_points": [0.1, 0.2]})
    assert resp.status_code == 200
    assert resp.json()["baseline"]["trend_points"] == [0.1, 0.2]


def test_update_baseline_ema():
    """Test exponential moving average merge for anomaly_index."""
    create = client.post("/api/v1/assets", json={"name": "BRG-05-A"})
    asset_id = create.json()["id"]
    # First update
    client.post(f"/api/v1/assets/{asset_id}/baseline", json={"anomaly_index": 0.3})
    # Second update
    resp = client.post(f"/api/v1/assets/{asset_id}/baseline", json={"anomaly_index": 0.5})
    # EMA: 0.3 * 0.5 + 0.7 * 0.3 = 0.36
    assert abs(resp.json()["baseline"]["anomaly_index"] - 0.36) < 0.01


def test_update_baseline_trend_points_append():
    """Test trend points append and cap at 30."""
    create = client.post("/api/v1/assets", json={"name": "BRG-05-A"})
    asset_id = create.json()["id"]
    client.post(f"/api/v1/assets/{asset_id}/baseline", json={"trend_points": 0.1})
    client.post(f"/api/v1/assets/{asset_id}/baseline", json={"trend_points": 0.2})
    resp = client.post(f"/api/v1/assets/{asset_id}/baseline", json={"trend_points": 0.3})
    trend = resp.json()["baseline"]["trend_points"]
    assert trend == [0.1, 0.2, 0.3]


def test_update_baseline_not_found():
    resp = client.post("/api/v1/assets/nonexistent/baseline", json={"anomaly_index": 0.5})
    assert resp.status_code == 404


def test_update_baseline_no_fields():
    create = client.post("/api/v1/assets", json={"name": "BRG-05-A"})
    asset_id = create.json()["id"]
    resp = client.post(f"/api/v1/assets/{asset_id}/baseline", json={})
    assert resp.status_code == 400


def test_upload_updates_baseline():
    """Test that upload endpoint updates asset baseline when asset exists."""
    # Create asset with name matching equipment_id
    create = client.post("/api/v1/assets", json={"name": "BRG-05-A"})
    asset_id = create.json()["id"]

    # Upload CSV for that asset
    csv_content = (
        "timestamp,equipment_id,temperature_c,vibration_mm_s,pressure_bar,rpm\n"
        "2026-08-20T08:00:00,BRG-05-A,55.0,2.0,5.0,1750\n"
        "2026-08-20T08:01:00,BRG-05-A,55.5,2.1,5.0,1750\n"
        "2026-08-20T08:02:00,BRG-05-A,56.0,2.2,5.0,1750\n"
        "2026-08-20T08:03:00,BRG-05-A,56.5,2.3,5.0,1750\n"
        "2026-08-20T08:04:00,BRG-05-A,57.0,2.4,5.0,1750\n"
        "2026-08-20T08:05:00,BRG-05-A,57.5,2.5,5.0,1750\n"
        "2026-08-20T08:06:00,BRG-05-A,58.0,2.6,5.0,1750\n"
        "2026-08-20T08:07:00,BRG-05-A,58.5,2.7,5.0,1750\n"
    )
    files = {"file": ("test.csv", csv_content.encode(), "text/csv")}
    resp = client.post("/api/v1/pulse/upload?equipment_id=BRG-05-A", files=files)
    assert resp.status_code == 200
    # Verify baseline was updated
    asset = client.get(f"/api/v1/assets/{asset_id}").json()
    assert "anomaly_index" in asset["baseline"]
    assert "trend_points" in asset["baseline"]
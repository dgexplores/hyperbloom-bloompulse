"""Asset registry CRUD + baseline persistence."""
import pytest
from backend.app.assets import AssetRegistry, Asset

def test_create_asset():
    reg = AssetRegistry()
    asset = reg.create(name="BRG-05-A", rpm=1750, bearing_type="6205")
    assert asset.id is not None
    assert asset.name == "BRG-05-A"
    assert asset.rpm == 1750
    assert asset.bearing_type == "6205"
    assert asset.baseline == {}

def test_get_asset():
    reg = AssetRegistry()
    created = reg.create(name="BRG-05-A", rpm=1750)
    fetched = reg.get(created.id)
    assert fetched.id == created.id
    assert fetched.name == "BRG-05-A"

def test_list_assets():
    reg = AssetRegistry()
    reg.create(name="BRG-05-A")
    reg.create(name="BRG-06-B")
    assets = reg.list()
    assert len(assets) == 2

def test_update_asset():
    reg = AssetRegistry()
    asset = reg.create(name="BRG-05-A")
    updated = reg.update(asset.id, {"rpm": 1800})
    assert updated.rpm == 1800

def test_delete_asset():
    reg = AssetRegistry()
    asset = reg.create(name="BRG-05-A")
    reg.delete(asset.id)
    assert reg.get(asset.id) is None

def test_baseline_persistence():
    reg = AssetRegistry()
    asset = reg.create(name="BRG-05-A")
    reg.update_baseline(asset.id, {"anomaly_index": 0.3, "trend_points": [0.1, 0.2]})
    fetched = reg.get(asset.id)
    assert fetched.baseline["anomaly_index"] == 0.3
    assert fetched.baseline["trend_points"] == [0.1, 0.2]

def test_baseline_merge_exponential_moving():
    reg = AssetRegistry()
    asset = reg.create(name="BRG-05-A")
    reg.update_baseline(asset.id, {"anomaly_index": 0.3})
    reg.update_baseline(asset.id, {"anomaly_index": 0.5})  # EMA with alpha=0.3
    fetched = reg.get(asset.id)
    # EMA: 0.3 * 0.5 + 0.7 * 0.3 = 0.15 + 0.21 = 0.36
    assert abs(fetched.baseline["anomaly_index"] - 0.36) < 0.01
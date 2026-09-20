"""Consumer-driven API contracts: every public endpoint returns the shape
its Pydantic model promises. Catches breaking changes without a broker."""
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models.schemas import (
    Asset as AssetSchema,
)
from backend.app.models.schemas import (
    Citation,
    Confidence,
    HealthResponse,
    PulseResponse,
)

client = TestClient(app)

CSV_10 = (
    "timestamp,equipment_id,temperature_c,vibration_mm_s,pressure_bar,rpm\n"
    + "2026-08-20T08:00:00,BRG-05-A,55.0,2.0,5.0,1750\n" * 10
).encode()


def _upload():
    resp = client.post(
        "/api/v1/pulse/upload?equipment_id=BRG-05-A",
        files={"file": ("c.csv", CSV_10, "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_health_contract():
    HealthResponse.model_validate(client.get("/api/v1/health").json())


def test_analyze_contract():
    body = _upload()
    PulseResponse.model_validate(body)
    for citation in body["citations"]:
        Citation.model_validate(citation)
        assert {"span_text", "locator", "deep_link", "confidence"} <= set(citation)
    Confidence.model_validate(body["confidence"])


def test_evidence_fields_present():
    body = _upload()
    for field in (
        "trend_ci", "physics_consistency", "physics_hz",
        "assumed_bearing", "seasonal_period", "conformal_set",
    ):
        assert field in body, field


def test_assets_contract():
    created = client.post("/api/v1/assets", json={"name": "CONTRACT-1"}).json()
    AssetSchema.model_validate(created)
    listed = client.get("/api/v1/assets").json()
    assert isinstance(listed, list)
    AssetSchema.model_validate(client.get(f"/api/v1/assets/{created['id']}").json())
    patched = client.patch(
        f"/api/v1/assets/{created['id']}", json={"rpm": 1800}
    ).json()
    assert patched["rpm"] == 1800
    assert client.delete(f"/api/v1/assets/{created['id']}").json()["deleted"] is True


def test_fleet_contract():
    client.post("/api/v1/assets", json={"name": "CONTRACT-FLEET"})
    summary = client.get("/api/v1/fleet/summary").json()
    assert isinstance(summary, list)
    assert summary, "fleet summary is empty right after creating an asset"
    entry = summary[0]
    assert {"id", "name", "trend_sparkline", "last_severity"} <= set(entry)
    filtered = client.get("/api/v1/fleet/filter?severity=normal&limit=5").json()
    assert isinstance(filtered, list)
    assert len(filtered) <= 5


def test_metrics_contract():
    body = client.get("/api/v1/metrics").json()
    assert {"requests_total", "errors_total", "verdicts",
            "latency_ms_p50", "latency_ms_p95"} <= set(body)


def test_error_contract():
    resp = client.post(
        "/api/v1/pulse/upload?equipment_id=X",
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    assert resp.status_code == 400
    assert isinstance(resp.json()["detail"], str)

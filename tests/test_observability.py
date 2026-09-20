"""Tests for observability (backend/app/observability.py).

Request IDs, JSON access logs, and the in-memory metrics endpoint. Metrics
are explicitly ephemeral (documented in the module): a serverless worker
starts counters at zero, which is fine for smoke checks and wrong for
billing — Phase 9 meters elsewhere.
"""
import json
import logging

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.observability import JSONFormatter, metrics


def test_request_id_present_and_unique():
    c = TestClient(app)
    first = c.get("/api/v1/health")
    second = c.get("/api/v1/health")
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.headers.get("x-request-id")
    assert second.headers.get("x-request-id")
    assert first.headers["x-request-id"] != second.headers["x-request-id"]


def test_request_id_echoed_when_provided():
    c = TestClient(app)
    resp = c.get("/api/v1/health", headers={"x-request-id": "probe-123"})
    assert resp.headers["x-request-id"] == "probe-123"


def test_metrics_endpoint_shape():
    c = TestClient(app)
    c.get("/api/v1/health")
    body = c.get("/api/v1/metrics").json()
    assert body["requests_total"] >= 2
    assert body["errors_total"] >= 0
    assert isinstance(body["verdicts"], dict)
    assert "latency_ms_p50" in body and "latency_ms_p95" in body
    assert body["latency_ms_p50"] >= 0


def test_upload_increments_verdict_bucket():
    c = TestClient(app)
    before = c.get("/api/v1/metrics").json()["verdicts"].get("critical", 0)
    csv = (
        "timestamp,equipment_id,temperature_c,vibration_mm_s,pressure_bar,rpm\n"
        + "2026-08-20T08:00:00,BRG-05-A,85.0,6.0,5.0,1750\n" * 10
    )
    resp = c.post(
        "/api/v1/pulse/upload?equipment_id=BRG-05-A",
        files={"file": ("m.csv", csv.encode(), "text/csv")},
    )
    assert resp.status_code == 200
    after = c.get("/api/v1/metrics").json()["verdicts"].get("critical", 0)
    assert after == before + 1


def test_json_formatter_emits_parseable_line():
    record = logging.LogRecord(
        name="bloompulse", level=logging.INFO, pathname=__file__, lineno=1,
        msg="hello", args=(), exc_info=None,
    )
    line = JSONFormatter().format(record)
    parsed = json.loads(line)
    assert parsed["message"] == "hello"
    assert parsed["level"] == "INFO"
    assert "timestamp" in parsed


def test_metrics_counters_are_module_scoped():
    assert metrics is not None
    assert hasattr(metrics, "record_request")
    assert hasattr(metrics, "record_verdict")
    assert hasattr(metrics, "snapshot")

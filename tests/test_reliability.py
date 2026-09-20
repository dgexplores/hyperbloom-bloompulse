"""Phase 7b: Sentry gate, API contracts, chaos middleware."""
import os

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.observability import ChaosMiddleware, init_sentry


def test_sentry_noop_without_dsn(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert init_sentry() is False


def test_sentry_skips_gracefully_without_sdk(monkeypatch):
    # sentry_sdk is intentionally NOT a dependency (bundle size); with a DSN
    # set but no SDK installed, init must warn and skip, never crash.
    monkeypatch.setenv("SENTRY_DSN", "https://example@sentry.io/1")
    assert init_sentry() is False


def test_chaos_middleware_is_importable():
    assert ChaosMiddleware is not None


def _upload(client, rows=10):
    csv = (
        "timestamp,equipment_id,temperature_c,vibration_mm_s,pressure_bar,rpm\n"
        + "2026-08-20T08:00:00,BRG-05-A,55.0,2.0,5.0,1750\n" * rows
    )
    return client.post(
        "/api/v1/pulse/upload?equipment_id=BRG-05-A",
        files={"file": ("c.csv", csv.encode(), "text/csv")},
    )


def test_chaos_off_by_default():
    os.environ.pop("CHAOS_ERROR_RATE", None)
    os.environ.pop("CHAOS_LATENCY_MS", None)
    resp = _upload(TestClient(app))
    assert resp.status_code == 200


def test_chaos_error_rate_force_fails(monkeypatch):
    monkeypatch.setenv("CHAOS_ERROR_RATE", "1.0")
    monkeypatch.setenv("CHAOS_LATENCY_MS", "0")
    codes = {
        _upload(TestClient(app)).status_code
        for _ in range(5)
    }
    assert codes == {500}


def test_chaos_latency_injected(monkeypatch):
    import time

    monkeypatch.setenv("CHAOS_ERROR_RATE", "0")
    monkeypatch.setenv("CHAOS_LATENCY_MS", "300")
    start = time.perf_counter()
    resp = _upload(TestClient(app))
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert resp.status_code == 200
    assert elapsed_ms >= 250

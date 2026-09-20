"""Observability: request IDs, JSON access logs, in-memory metrics.

Metrics are explicitly ephemeral: each serverless worker starts its counters
at zero. Good enough for smoke checks and debugging, wrong for billing or
SLOs — Phase 9 meters durably elsewhere. The verdict counters only move on
requests this worker actually served.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import threading
import time
import uuid
from collections import Counter, deque
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

request_id_ctx: ContextVar[str] = ContextVar("bloompulse_request_id", default="-")


def init_sentry() -> bool:
    """Initialize Sentry only when configured AND installed.

    sentry_sdk is deliberately not a dependency (function bundle budget),
    so a DSN without the SDK warns and skips instead of crashing.
    """
    dsn = os.getenv("SENTRY_DSN", "")
    if not dsn:
        return False
    try:
        import sentry_sdk  # type: ignore[import-not-found]
    except ImportError:
        logging.getLogger("bloompulse").warning(
            "SENTRY_DSN is set but sentry_sdk is not installed; skipping."
        )
        return False
    sentry_sdk.init(dsn=dsn, traces_sample_rate=0.1)
    return True


class ChaosMiddleware(BaseHTTPMiddleware):
    """Fault injection for resilience drills. Off unless env-armed.

    CHAOS_LATENCY_MS: added sleep per request. CHAOS_ERROR_RATE: fraction
    of requests answered 500. Read per request so tests can arm it live.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        latency_ms = float(os.getenv("CHAOS_LATENCY_MS", "0") or 0)
        if latency_ms > 0:
            await asyncio.sleep(latency_ms / 1000.0)
        try:
            error_rate = float(os.getenv("CHAOS_ERROR_RATE", "0") or 0)
        except ValueError:
            error_rate = 0.0
        if error_rate > 0 and random.random() < error_rate:
            return JSONResponse(status_code=500, content={"detail": "chaos injected"})
        return await call_next(request)


class JSONFormatter(logging.Formatter):
    """One JSON object per line: timestamp, level, message, request_id."""

    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_ctx.get(),
        })


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assign (or echo) X-Request-ID, time the request, log one JSON line."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        request_id_ctx.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            metrics.record_request(request.url.path, 500, 0.0)
            raise
        latency_ms = (time.perf_counter() - started) * 1000.0
        response.headers["x-request-id"] = request_id
        metrics.record_request(request.url.path, response.status_code, latency_ms)
        logging.getLogger("bloompulse.access").info(
            json.dumps({
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "latency_ms": round(latency_ms, 1),
            })
        )
        return response


class MetricsRegistry:
    """Thread-safe counters plus a bounded latency ring."""

    def __init__(self, ring_size: int = 512) -> None:
        self._lock = threading.Lock()
        self._requests = 0
        self._errors = 0
        self._verdicts: Counter[str] = Counter()
        self._latencies: deque[float] = deque(maxlen=ring_size)

    def record_request(self, path: str, status: int, latency_ms: float) -> None:
        with self._lock:
            self._requests += 1
            if status >= 500:
                self._errors += 1
            self._latencies.append(latency_ms)

    def record_verdict(self, severity: str, latency_ms: float) -> None:
        with self._lock:
            self._verdicts[severity] += 1

    def snapshot(self) -> dict:
        with self._lock:
            lat = sorted(self._latencies)
            def pct(q: float) -> float:
                if not lat:
                    return 0.0
                return round(lat[min(len(lat) - 1, int(q * len(lat)))], 1)
            return {
                "requests_total": self._requests,
                "errors_total": self._errors,
                "verdicts": dict(self._verdicts),
                "latency_ms_p50": pct(0.50),
                "latency_ms_p95": pct(0.95),
            }


metrics = MetricsRegistry()

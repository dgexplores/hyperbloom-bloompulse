"""BloomPulse API - offline, citation-grounded, no API keys needed to demo."""
from __future__ import annotations

import csv
import hmac
import io
import logging
import os
import time
from collections import deque

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.models.schemas import (
    AnomalyResult, Confidence, EquipmentType, HealthResponse,
    PulseRequest, PulseResponse, SensorReading,
)
from backend.app.rag.citations import citations_for, corpus_version
from model.anomaly import (
    PRESSURE_VARIANCE_ALERT, TEMP_RISE_THRESHOLD, VIB_ALERT, VIB_NORMAL,
    score_readings,
)

logger = logging.getLogger("bloompulse")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

MAX_ROWS = 500
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
REQUIRED_COLUMNS = {"timestamp", "temperature_c", "vibration_mm_s"}

# Simple fixed-window limiter. The analyse endpoints are unauthenticated and do
# real CPU work, so an open deployment needs some backstop.
# ponytail: in-process counters, fine for one worker. Move to Redis if this
# ever runs multi-process behind a load balancer.
RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
_hits: dict[str, deque[float]] = {}

API_KEY = os.getenv("API_KEY", "")
# Comma-separated allowlist. Default open, because the demo is public and
# carries no credentials or user data.
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]

app = FastAPI(title="BloomPulse - Industrial Sensor Sentinel", version="0.1.0-pulse")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    # Wildcard origins and credentials are mutually exclusive per the CORS
    # spec, and browsers reject the combination outright.
    allow_credentials="*" not in CORS_ORIGINS,
)


def rate_limit(request: Request) -> None:
    if RATE_LIMIT <= 0:
        return
    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    seen = _hits.setdefault(client, deque())
    while seen and now - seen[0] > 60:
        seen.popleft()
    if len(seen) >= RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"More than {RATE_LIMIT} requests in a minute. Wait and retry.",
            headers={"Retry-After": "60"},
        )
    seen.append(now)


def require_api_key(request: Request) -> None:
    """No-op unless API_KEY is set, keeping the public demo keyless."""
    if not API_KEY:
        return
    presented = request.headers.get("x-api-key") or ""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        presented = auth[7:]
    if not hmac.compare_digest(presented, API_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception) -> JSONResponse:
    """Last resort. Log the trace, return a clean body, never leak internals."""
    logger.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal error"})


def parse_sensor_csv(raw: bytes, default_equipment_id: str) -> list[SensorReading]:
    """Bytes to validated readings, raising HTTP 400 with an actionable message.

    Every rejection a user can trigger is answered here, so callers never see
    a KeyError, a ValueError or a decoding failure surface as a 500.
    """
    if not raw.strip():
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="File is not UTF-8 text. Export the sheet as a plain CSV and retry.",
        )

    reader = csv.DictReader(io.StringIO(text))
    columns = {(c or "").strip() for c in (reader.fieldnames or [])}
    missing = REQUIRED_COLUMNS - columns
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"CSV is missing required column(s): {', '.join(sorted(missing))}. "
                   f"Expected header: timestamp, equipment_id, temperature_c, "
                   f"vibration_mm_s, pressure_bar, rpm",
        )

    def number(row: dict, key: str, line: int, default: float | None = None) -> float | None:
        value = (row.get(key) or "").strip()
        if not value:
            if default is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Row {line}: '{key}' is empty and has no default.",
                )
            return default
        try:
            return float(value)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Row {line}: '{key}' is {value!r}, which is not a number.",
            )

    readings: list[SensorReading] = []
    for line, row in enumerate(reader, start=2):  # line 1 is the header
        if not any((v or "").strip() for v in row.values()):
            continue  # tolerate blank lines, including a trailing newline
        if len(readings) >= MAX_ROWS:
            raise HTTPException(
                status_code=400,
                detail=f"CSV has more than {MAX_ROWS} data rows. "
                       f"Split the file or trim it to the most recent {MAX_ROWS}.",
            )
        timestamp = (row.get("timestamp") or "").strip()
        if not timestamp:
            raise HTTPException(status_code=400, detail=f"Row {line}: 'timestamp' is empty.")
        readings.append(SensorReading(
            timestamp=timestamp,
            equipment_id=(row.get("equipment_id") or "").strip() or default_equipment_id,
            temperature_c=number(row, "temperature_c", line),
            vibration_mm_s=number(row, "vibration_mm_s", line),
            pressure_bar=number(row, "pressure_bar", line, default=5.0),
            rpm=number(row, "rpm", line, default=1750.0),
        ))

    if not readings:
        raise HTTPException(
            status_code=400,
            detail="CSV has a header but no data rows.",
        )
    return readings


CONFIDENCE_FLOOR = 70.0  # below this the verdict is reported as an abstention


def _confidence(result: dict) -> Confidence:
    """Certainty in the verdict, not the severity of it.

    A clean machine is a high-confidence "normal". The genuinely uncertain
    case is "monitor", where readings have drifted from baseline but cleared
    no published limit, so the call between normal and alert is unsupported.
    """
    severity = result["severity"]
    m = result["metrics"]
    drivers = [
        name for name, value, limit in (
            ("vibration", m["max_vib"], VIB_ALERT),
            ("temperature rise", m["max_temp_rise"], TEMP_RISE_THRESHOLD),
            ("pressure variance", m["pressure_var"], PRESSURE_VARIANCE_ALERT),
        ) if value > limit
    ]

    if severity == "critical":
        if len(drivers) >= 2:
            score = 92.0
            rationale = (f"{len(drivers)} independent channels are past their limits "
                         f"({', '.join(drivers)}), and they agree.")
        else:
            score = 85.0
            rationale = (f"Vibration {m['max_vib']} mm/s is past the ISO 10816-3 Zone D "
                         f"shutdown limit of {VIB_ALERT} mm/s.")
    elif severity == "alert":
        score = 84.0
        rationale = (f"{result['contributing_feature'].replace('_', ' ').capitalize()} "
                     f"has crossed its ISO/NTN threshold, with no second channel "
                     f"confirming it yet.")
    elif severity == "monitor":
        score = 62.0
        rationale = ("Readings have drifted from baseline but clear every published "
                     "limit. The call between normal and alert is not yet supported.")
    else:
        score = 88.0
        rationale = (f"Vibration peaks at {m['max_vib']} mm/s against a {VIB_NORMAL} mm/s "
                     f"Zone B/C boundary, and temperature is within "
                     f"{m['max_temp_rise']} C of baseline. Comfortably inside Zone A/B.")

    # A breached published limit is a measurement, not an inference, so it
    # stands on its own even when the series was too short or too flat to
    # model. The cap below applies only where the model was doing the work.
    if not result.get("baseline_modeled", True) and not drivers:
        score = min(score, 60.0)
        rationale = (f"{result.get('reading_count')} reading(s) with no usable variation, "
                     f"so no baseline could be modelled. Nothing here crosses a published "
                     f"limit either, which is why this is not a verdict.")

    return Confidence(score=score, rationale=rationale, abstain=score < CONFIDENCE_FLOOR)


def _work_order(equipment_id: str, equipment_type: EquipmentType, result: dict) -> dict:
    severity = result["severity"]
    urgent = severity in ("alert", "critical")
    return {
        "equipment_id": equipment_id,
        "equipment_type": equipment_type.value,
        "action": ("Immediate shutdown and bearing inspection" if severity == "critical"
                   else "Schedule inspection within 72 hours" if severity == "alert"
                   else "Continue monitoring, next check in 14 days"),
        "parts": ["NTN UCFCX05 bearing", "ISO VG68 lubricant"] if urgent else [],
        "estimated_downtime_hours": 4 if severity == "critical" else 1 if severity == "alert" else 0,
        "safety_lockout_required": urgent,
        "regulation": "OSHA 1910.147 + ISO 10816-3",
    }


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(corpus_version=corpus_version())


@app.get("/api/v1/corpus/version", dependencies=[Depends(require_api_key), Depends(rate_limit)])
def corpus_ver() -> dict:
    return {"corpus_version": corpus_version(), "free_tier": True}


@app.post("/api/v1/pulse/analyze", response_model=PulseResponse,
          dependencies=[Depends(require_api_key), Depends(rate_limit)])
def analyze(req: PulseRequest) -> PulseResponse:
    started = time.perf_counter()
    result = score_readings([r.model_dump() for r in req.readings])
    metrics = result["metrics"]
    severity = result["severity"]
    driver = result["contributing_feature"].replace("_", " ")

    anomaly = AnomalyResult(
        equipment_id=req.equipment_id,
        is_anomaly=severity in ("alert", "critical"),
        anomaly_score=result["anomaly_score"],
        failure_probability_7d=result["failure_probability_7d"],
        predicted_failure_days=result["predicted_failure_days"],
        contributing_feature=result["contributing_feature"],
        severity=severity,
        explanation=(
            f"Anomaly score {result['anomaly_score']} is driven by {driver} "
            f"(vibration {metrics['max_vib']} mm/s, temperature {metrics['max_temp_rise']} C "
            f"above baseline, pressure variance {metrics['pressure_var']}%). "
            + ("Lockout under 1910.147 is required before service."
               if severity in ("alert", "critical")
               else "Keep to the routine ISO 10816-3 monitoring interval.")
        ),
        explanation_simple=(
            f"{req.equipment_id} is {severity}. The main problem is {driver}. "
            + ("Stop the machine and inspect it within 3 days." if severity == "critical"
               else "Book an inspection this week." if severity == "alert"
               else "Nothing to do, keep it running.")
        ),
    )

    return PulseResponse(
        anomaly=anomaly,
        readings=req.readings,
        citations=citations_for(result),
        confidence=_confidence(result),
        work_order=_work_order(req.equipment_id, req.equipment_type, result),
        corpus_version=corpus_version(),
        latency_ms=int((time.perf_counter() - started) * 1000),
    )


@app.post("/api/v1/pulse/upload", response_model=PulseResponse,
          dependencies=[Depends(require_api_key), Depends(rate_limit)])
async def upload_csv(
    file: UploadFile = File(...),
    equipment_id: str = "BRG-05-A",
    equipment_type: EquipmentType = EquipmentType.BEARING,
) -> PulseResponse:
    # Bounded read, so an oversized upload is refused rather than buffered.
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {MAX_UPLOAD_BYTES // 1024 // 1024}MB limit.",
        )
    readings = parse_sensor_csv(raw, default_equipment_id=equipment_id)
    return analyze(PulseRequest(
        equipment_id=equipment_id, equipment_type=equipment_type, readings=readings,
    ))


@app.get("/")
def root() -> dict:
    return {
        "name": "BloomPulse",
        "docs": "/docs",
        "health": "/health",
        "analyze": "POST /api/v1/pulse/analyze",
        "upload": "POST /api/v1/pulse/upload",
    }

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
    AnomalyResult, Asset as AssetSchema, Confidence, EquipmentType, HealthResponse,
    PulseRequest, PulseResponse, SensorReading,
)
from backend.app.assets import AssetRegistry
# Lazy import to avoid bundling pandas/pyarrow in Vercel function
def _get_parsers():
    import sys
    utils_path = os.path.join(os.path.dirname(__file__), '..', '..', 'utils')
    if utils_path not in sys.path:
        sys.path.insert(0, utils_path)
    from parsers import parse_sensor_data, df_to_sensor_readings, ParseError
    return parse_sensor_data, df_to_sensor_readings, ParseError
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
_last_sweep = 0.0

# How many proxies sit between the caller and this process. One on Vercel, where
# the edge terminates the connection. Set to 0 to ignore forwarded headers.
TRUSTED_PROXY_HOPS = int(os.getenv("TRUSTED_PROXY_HOPS", "1"))

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

# Asset registry (in-memory, swappable for Postgres in Phase 4)
asset_registry = AssetRegistry()


def _client_ip(request: Request) -> str:
    """The caller's address, as far as the deployment lets us know it.

    Behind a proxy `request.client.host` is the proxy, so keying on it puts
    every visitor in one bucket and the public demo rate-limits everybody at
    once. The forwarded chain is only consulted when the deployment declares
    that a proxy really is in front of us.
    """
    if TRUSTED_PROXY_HOPS > 0:
        chain = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]
        if chain:
            # Rightmost entries were appended by the closest proxies; the caller
            # is TRUSTED_PROXY_HOPS places in from the right.
            index = max(0, len(chain) - TRUSTED_PROXY_HOPS)
            return chain[index]
    return request.client.host if request.client else "unknown"


def _sweep(now: float) -> None:
    """Drop buckets that have gone quiet, so the limiter cannot grow forever."""
    global _last_sweep
    if now - _last_sweep < 60:
        return
    _last_sweep = now
    for key in [k for k, v in _hits.items() if not v or now - v[-1] > 60]:
        del _hits[key]


def rate_limit(request: Request) -> None:
    if RATE_LIMIT <= 0:
        return
    client = _client_ip(request)
    now = time.monotonic()
    _sweep(now)
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


def _describe_rise(delta: float) -> str:
    """Temperature change against baseline, worded for its direction."""
    if delta > 0.5:
        return f"{delta} C above baseline"
    if delta < -0.5:
        return f"{abs(delta)} C below baseline"
    return "level with baseline"


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
        elif drivers:
            score = 85.0
            rationale = (f"{drivers[0].capitalize()} is past its published limit, and no "
                         f"second channel confirms it yet.")
        else:
            # The gates did not fire, so the model did the escalating. Say that,
            # rather than naming a vibration reading that never crossed anything.
            score = 78.0
            rationale = ("Readings have moved clear of this machine's own baseline, "
                         "though nothing published has been crossed yet.")
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
                     f"Zone B/C boundary, and temperature sits "
                     f"{_describe_rise(m['max_temp_rise'])}. Comfortably inside Zone A/B.")

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


# Both paths exist on purpose. /health is the conventional one and works when
# the app is run directly, while the deployed SPA rewrite sends everything that
# is not under /api to index.html, so probes in production need the /api path.
@app.get("/health", response_model=HealthResponse)
@app.get("/api/v1/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(corpus_version=corpus_version())


@app.get("/api/v1/corpus/version", dependencies=[Depends(require_api_key), Depends(rate_limit)])
def corpus_ver() -> dict:
    return {"corpus_version": corpus_version(), "free_tier": True}


# Asset Registry endpoints
from pydantic import BaseModel
from typing import Optional


class AssetCreate(BaseModel):
    name: str
    rpm: int = 1750
    bearing_type: str = "6205"
    install_date: Optional[str] = None


from pydantic import BaseModel, field_validator
from typing import Optional, Union, Literal


class AssetCreate(BaseModel):
    name: str
    rpm: int = 1750
    bearing_type: str = "6205"
    install_date: Optional[str] = None


class AssetUpdate(BaseModel):
    name: Optional[str] = None
    rpm: Optional[int] = None
    bearing_type: Optional[str] = None
    install_date: Optional[str] = None


class BaselineUpdate(BaseModel):
    anomaly_index: Optional[float] = None
    trend_points: Optional[Union[float, list[float]]] = None

    @field_validator("trend_points", mode="before")
    @classmethod
    def _coerce_trend_points(cls, v):
        if isinstance(v, (int, float)):
            return [float(v)]
        return v


@app.post("/api/v1/assets", dependencies=[Depends(require_api_key), Depends(rate_limit)])
def create_asset(payload: AssetCreate) -> AssetSchema:
    asset = asset_registry.create(
        name=payload.name,
        rpm=payload.rpm,
        bearing_type=payload.bearing_type,
        install_date=payload.install_date,
    )
    return AssetSchema.model_validate(asset)


@app.get("/api/v1/assets", dependencies=[Depends(require_api_key), Depends(rate_limit)])
def list_assets() -> list[AssetSchema]:
    return [AssetSchema.model_validate(a) for a in asset_registry.list()]


@app.get("/api/v1/assets/{asset_id}", dependencies=[Depends(require_api_key), Depends(rate_limit)])
def get_asset(asset_id: str) -> AssetSchema:
    asset = asset_registry.get(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return AssetSchema.model_validate(asset)


@app.patch("/api/v1/assets/{asset_id}", dependencies=[Depends(require_api_key), Depends(rate_limit)])
def update_asset(asset_id: str, payload: AssetUpdate) -> AssetSchema:
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    asset = asset_registry.update(asset_id, data)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return AssetSchema.model_validate(asset)


@app.delete("/api/v1/assets/{asset_id}", dependencies=[Depends(require_api_key), Depends(rate_limit)])
def delete_asset(asset_id: str) -> dict:
    if not asset_registry.delete(asset_id):
        raise HTTPException(status_code=404, detail="Asset not found")
    return {"deleted": True, "asset_id": asset_id}


@app.post("/api/v1/assets/{asset_id}/baseline", dependencies=[Depends(require_api_key), Depends(rate_limit)])
def update_baseline(asset_id: str, payload: BaselineUpdate) -> AssetSchema:
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="No baseline fields to update")
    asset = asset_registry.update_baseline(asset_id, data)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return AssetSchema.model_validate(asset)
    return asset


@app.post("/api/v1/pulse/analyze", response_model=PulseResponse,
          dependencies=[Depends(require_api_key), Depends(rate_limit)])
def analyze(req: PulseRequest) -> PulseResponse:
    started = time.perf_counter()
    result = score_readings([r.model_dump() for r in req.readings])
    metrics = result["metrics"]
    severity = result["severity"]
    driver = result["contributing_feature"].replace("_", " ")
    urgent = severity in ("alert", "critical")

    advice = {
        "critical": f"The problem is {driver}. Stop the machine and inspect it within 3 days.",
        "alert": f"The problem is {driver}. Book an inspection this week.",
        "monitor": f"Nothing is over a limit yet, but {driver} is the one to watch.",
        "normal": "Nothing is near a limit. Keep it running.",
    }

    anomaly = AnomalyResult(
        equipment_id=req.equipment_id,
        is_anomaly=urgent,
        anomaly_index=result["anomaly_index"],
        inspection_window_days=result["inspection_window_days"],
        contributing_feature=result["contributing_feature"],
        severity=severity,
        explanation=" ".join([
            f"Anomaly index {result['anomaly_index']} is driven by {driver}." if urgent
            else f"Anomaly index {result['anomaly_index']}. The channel furthest from its "
                 f"own baseline is {driver}, and every published limit still holds.",
            f"Vibration {metrics['max_vib']} mm/s, temperature "
            f"{_describe_rise(metrics['max_temp_rise'])}, pressure variance "
            f"{metrics['pressure_var']}%.",
            "Lockout under 1910.147 is required before service." if urgent
            else "Keep to the routine ISO 10816-3 monitoring interval.",
        ]),
        explanation_simple=f"{req.equipment_id} is {severity}. {advice[severity]}",
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
async def upload_sensor_data(
    file: UploadFile = File(...),
    equipment_id: str = "BRG-05-A",
    equipment_type: EquipmentType = EquipmentType.BEARING,
) -> PulseResponse:
    # Async handler for proper exception handling
    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {MAX_UPLOAD_BYTES // 1024 // 1024}MB limit.",
        )

    # Parse using multi-format parser (auto-detects CSV, JSONL, Excel, Parquet)
    # Lazy import to avoid bundling pandas/pyarrow in Vercel function
    parse_sensor_data, df_to_sensor_readings, ParseError = _get_parsers()
    try:
        df = parse_sensor_data(raw, filename=file.filename)
    except ParseError as e:
        raise HTTPException(status_code=400, detail=str(e))

    readings = df_to_sensor_readings(df, default_equipment_id=equipment_id)
    response = analyze(PulseRequest(
        equipment_id=equipment_id, equipment_type=equipment_type, readings=readings,
    ))

    # Persist baseline if asset exists
    asset = asset_registry.get_by_name(equipment_id)
    if asset:
        anomaly_index = response.anomaly.anomaly_index
        asset_registry.update_baseline(asset.id, {
            "anomaly_index": anomaly_index,
            "trend_points": anomaly_index,
        })

    return response


def _severity_from_index(idx: float) -> str:
    """Map anomaly_index to severity."""
    if idx < 0.50:
        return "normal"
    elif idx < 0.65:
        return "monitor"
    elif idx < 0.82:
        return "alert"
    else:
        return "critical"


class FleetAssetSummary(BaseModel):
    """Fleet summary entry for dashboard."""
    id: str
    name: str
    rpm: int
    bearing_type: str
    last_verdict: float | None = None
    last_severity: str | None = None
    last_timestamp: str | None = None
    trend_sparkline: list[float] = []


@app.get("/api/v1/fleet/summary", dependencies=[Depends(require_api_key), Depends(rate_limit)])
def fleet_summary() -> list[FleetAssetSummary]:
    """Fleet dashboard: all assets with last verdict and trend sparkline."""
    assets = asset_registry.list()
    summary = []
    for asset in assets:
        # Get trend points from baseline
        trend_points = asset.baseline.get("trend_points", [])
        if not isinstance(trend_points, list):
            trend_points = []

        # Get last anomaly index from trend points
        last_verdict = trend_points[-1] if trend_points else None
        last_severity = _severity_from_index(last_verdict) if last_verdict is not None else None
        last_timestamp = asset.updated_at if trend_points else None

        # Cap sparkline at 30 points
        sparkline = trend_points[-30:] if trend_points else []

        summary.append(FleetAssetSummary(
            id=asset.id,
            name=asset.name,
            rpm=asset.rpm,
            bearing_type=asset.bearing_type,
            last_verdict=last_verdict,
            last_severity=last_severity,
            last_timestamp=last_timestamp,
            trend_sparkline=sparkline,
        ))
    return summary


@app.get("/api/v1/fleet/filter", dependencies=[Depends(require_api_key), Depends(rate_limit)])
def fleet_filter(
    severity: Optional[Literal["normal", "monitor", "alert", "critical"]] = None,
    limit: int = 50,
) -> list[FleetAssetSummary]:
    """Filter fleet by severity with pagination."""
    if severity is not None and severity not in ("normal", "monitor", "alert", "critical"):
        raise HTTPException(status_code=400, detail=f"Invalid severity: {severity}")

    assets = asset_registry.list()
    filtered = []

    for asset in assets:
        trend_points = asset.baseline.get("trend_points", [])
        if not isinstance(trend_points, list) or not trend_points:
            asset_severity = "normal"  # no data = normal
        else:
            last_idx = trend_points[-1]
            asset_severity = _severity_from_index(last_idx)

        if severity is None or asset_severity == severity:
            sparkline = trend_points[-30:] if trend_points else []
            filtered.append(FleetAssetSummary(
                id=asset.id,
                name=asset.name,
                rpm=asset.rpm,
                bearing_type=asset.bearing_type,
                last_verdict=trend_points[-1] if trend_points else None,
                last_severity=asset_severity,
                last_timestamp=asset.updated_at if trend_points else None,
                trend_sparkline=sparkline,
            ))

    return filtered[:limit]


@app.get("/")
def root() -> dict:
    return {
        "name": "BloomPulse",
        "docs": "/docs",
        "health": "/health",
        "analyze": "POST /api/v1/pulse/analyze",
        "upload": "POST /api/v1/pulse/upload",
    }

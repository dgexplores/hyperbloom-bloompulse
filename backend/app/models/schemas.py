"""Pydantic contracts for BloomPulse - Sensor + Citation."""
from datetime import datetime
from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

class EquipmentType(str, Enum):
    BEARING = "bearing"
    MOTOR = "motor"
    PUMP = "pump"
    CNC = "cnc"
    COMPRESSOR = "compressor"

class Citation(BaseModel):
    id: str
    source_type: Literal["statute", "standard", "manual", "directive"]
    title: str
    # Verbatim, parsed straight out of corpus/sources/*.md. Never rewritten.
    span_text: str
    deep_link: str
    locator: str
    # sha256 of the corpus file this span was read from, so a claim can be
    # traced to an exact revision of the source document.
    version_hash: str
    # Why this passage was attached to this particular verdict.
    applies_to: str | None = None
    # True where the excerpt was written for the demo rather than taken from a
    # published document. The default is True on purpose: a passage has to
    # declare its published provenance (see corpus/sources/*.md) to be shown as
    # published text. The old default was False, cleared by the literal string
    # "synthetic" appearing anywhere in the section, so an invented passage that
    # did not use that word was presented as a standard.
    synthetic: bool = True
    # Authority confidence, not fidelity: 1.0 quotes a published source,
    # 0.6 is demo-written guidance. The span itself is always verbatim.
    confidence: float = 1.0

class Confidence(BaseModel):
    score: float = Field(ge=0, le=100)
    rationale: str
    abstain: bool = False

class SensorReading(BaseModel):
    timestamp: str
    equipment_id: str
    equipment_type: EquipmentType = EquipmentType.BEARING
    temperature_c: float
    vibration_mm_s: float
    pressure_bar: float | None = None
    rpm: float | None = None

class AnomalyResult(BaseModel):
    equipment_id: str
    is_anomaly: bool
    # 0..1 index of how far the machine has moved from its own baseline. It is
    # deliberately NOT called a probability: nothing in this project is
    # calibrated against failure events, so a probability claim could not be
    # supported.
    anomaly_index: float = Field(ge=0, le=1)
    # How soon the verdict says to look at the machine. A policy lookup on
    # severity, not a prediction of when failure occurs.
    inspection_window_days: int | None = None
    contributing_feature: str
    severity: Literal["normal", "monitor", "alert", "critical"]
    explanation: str
    explanation_simple: str | None = None

class PulseRequest(BaseModel):
    equipment_id: str = Field(default="BRG-05-A")
    equipment_type: EquipmentType = EquipmentType.BEARING
    readings: list[SensorReading] = Field(min_length=1, max_length=500)
    include_simple: bool = True

class PulseResponse(BaseModel):
    anomaly: AnomalyResult
    # Echoed back so a client charts exactly the series that was scored,
    # instead of parsing the CSV a second time and drifting from the server.
    readings: list[SensorReading]
    citations: list[Citation]
    confidence: Confidence
    work_order: dict
    corpus_version: str
    disclaimer: str = "Information only — not a substitute for certified inspection. Verify at source links before acting."
    latency_ms: int | None = None
    free_tier: bool = True
    # Instrument evidence. trend_ci is the 95% bootstrap interval of the
    # driving displacement (trend-z units); physics_consistency scores
    # heat/vibration agreement; physics_hz guides a handheld analyser under
    # the stated assumed bearing; seasonal_period reports a detected cycle.
    trend_ci: list[float] | None = None
    physics_consistency: float | None = None
    physics_hz: dict[str, float] | None = None
    assumed_bearing: str | None = None
    seasonal_period: int | None = None
    conformal_set: list[int] | None = None

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0-pulse"
    corpus_version: str = "bloompulse-2026.08.31-v1"


class Asset(BaseModel):
    id: str
    name: str
    rpm: int = 1750
    bearing_type: str = "6205"
    install_date: str | None = None
    baseline: dict = Field(default_factory=dict)
    created_at: str
    updated_at: str

    model_config = ConfigDict(from_attributes=True)

"""Pydantic contracts for BloomPulse - Sensor + Citation."""
from datetime import datetime
from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field

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
    span_text: str
    deep_link: str
    locator: str
    version_hash: str

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
    anomaly_score: float = Field(ge=0, le=1)
    failure_probability_7d: float = Field(ge=0, le=1)
    predicted_failure_days: int | None = None
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

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0-pulse"
    corpus_version: str = "bloompulse-2026.08.31-v1"

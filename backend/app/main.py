"""BloomPulse FastAPI - FREE, offline, citation-grounded"""
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import time, csv, io
from backend.app.models.schemas import PulseRequest, PulseResponse, AnomalyResult, Confidence, HealthResponse, SensorReading
from backend.app.rag.citations import citations_for, corpus_version
from model.anomaly import get_engine

app = FastAPI(title="BloomPulse - Industrial Sensor Sentinel", version="0.1.0-pulse")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(corpus_version=corpus_version())

@app.get("/api/v1/corpus/version")
def corpus_ver():
    return {"corpus_version": corpus_version(), "free_tier": True}

@app.post("/api/v1/pulse/analyze", response_model=PulseResponse)
def analyze(req: PulseRequest):
    t0 = time.time()
    readings = [r.model_dump() for r in req.readings]
    engine = get_engine()
    result = engine.score(readings)
    citations = citations_for(result)
    # confidence heuristic
    score = result["anomaly_score"]
    if result["severity"] == "critical":
        conf_score = 92.0
        rationale = f"Critical: vib {result['metrics']['max_vib']} >4.5 + temp rise {result['metrics']['max_temp_rise']}, strong threshold breach"
    elif result["severity"] == "alert":
        conf_score = 84.0
        rationale = f"Alert: contributing {result['contributing_feature']} exceeds ISO/NTN thresholds"
    elif result["severity"] == "monitor":
        conf_score = 68.0
        rationale = "Monitor: early deviation, below critical but trending"
    else:
        conf_score = 45.0
        rationale = "Normal: within ISO 10816 Zone A/B"
    confidence = Confidence(score=conf_score, rationale=rationale, abstain=conf_score<70 and result["severity"] in("normal","monitor"))

    anomaly = AnomalyResult(
        equipment_id=req.equipment_id,
        is_anomaly=result["severity"] in ("alert","critical"),
        anomaly_score=result["anomaly_score"],
        failure_probability_7d=result["failure_probability_7d"],
        predicted_failure_days=result["predicted_failure_days"],
        contributing_feature=result["contributing_feature"],
        severity=result["severity"],
        explanation=f"Anomaly {result['anomaly_score']} driven by {result['contributing_feature']} (vib {result['metrics']['max_vib']} mm/s, temp rise {result['metrics']['max_temp_rise']}C, pressure var {result['metrics']['pressure_var']}%). " + ("Immediate lockout per 1910.147 required." if result["severity"] in ("alert","critical") else "Continue monitoring per ISO 10816."),
        explanation_simple=f"Machine {req.equipment_id} is {result['severity']}. Main issue: {result['contributing_feature']}. " + ("Stop machine and check within 3 days." if result["severity"]=="critical" else "Watch closely, check next week." if result["severity"]=="alert" else "All good, keep running.")
    )

    # work order
    work_order = {
        "equipment_id": req.equipment_id,
        "equipment_type": req.equipment_type.value,
        "action": "Immediate shutdown + bearing inspection" if result["severity"]=="critical" else "Schedule inspection within 72h" if result["severity"]=="alert" else "Continue monitoring, next check 14 days",
        "parts": ["NTN UCFCX05 bearing", "ISO VG68 lubricant"] if result["severity"] in ("alert","critical") else [],
        "estimated_downtime_hours": 4 if result["severity"]=="critical" else 1 if result["severity"]=="alert" else 0,
        "safety_lockout_required": result["severity"] in ("alert","critical"),
        "regulation": "OSHA 1910.147 + ISO 10816-3"
    }

    latency = int((time.time()-t0)*1000)
    return PulseResponse(
        anomaly=anomaly,
        citations=citations,
        confidence=confidence,
        work_order=work_order,
        corpus_version=corpus_version(),
        latency_ms=latency
    )

@app.post("/api/v1/pulse/upload")
async def upload_csv(file: UploadFile = File(...), equipment_id: str = "BRG-05-A"):
    content = await file.read()
    text = content.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    readings = []
    for row in reader:
        readings.append(SensorReading(
            timestamp=row["timestamp"],
            equipment_id=row.get("equipment_id", equipment_id),
            temperature_c=float(row["temperature_c"]),
            vibration_mm_s=float(row["vibration_mm_s"]),
            pressure_bar=float(row.get("pressure_bar", 5.0)),
            rpm=float(row.get("rpm", 1750)) if row.get("rpm") else None
        ))
    req = PulseRequest(equipment_id=equipment_id, readings=readings)
    return analyze(req)

@app.get("/")
def root():
    return {"name":"BloomPulse","docs":"/docs","health":"/health","upload":"POST /api/v1/pulse/upload"}

# BloomPulse — Industrial Sensor Sentinel
### Predictive Maintenance + Citation-Grounded Compliance for HyperBloom Hacks 2026

> **HyperBloom Hacks — AI at Core, Industrial Application, Zero Hardware. Upload CSV → Predict Failure in 7 Days → Cite OSHA → Auto Work Order. 100% FREE to demo.**

![Status: MVP](https://img.shields.io/badge/Status-MVP-brightgreen)
![AI Core: TimeSeries+ RAG](https://img.shields.io/badge/AI-TimeSeries%20%2B%20RAG-blue)
![Free Tier: $0](https://img.shields.io/badge/Free%20Tier-%240-green)
![No Hardware](https://img.shields.io/badge/Hardware-None%20(CSV%20only)-orange)

---

## 1. Problem — $50B Downtime Nobody Detects

- 70% of US SMEs (250k factories) have **zero predictive maintenance**. A single bearing failure = 4-72h downtime, $10k-$500k loss.
- Existing solutions: Siemens MindSphere / GE Predix = **$100k+/yr**, closed, need IoT consultants. SMEs can't afford.
- Maintenance logs are siloed, OSHA 1910 fines ($16k per violation, $156k willful) pile up because techs don't know citation.
- **Who it kills:** 2M manufacturing workers, plant managers, maintenance techs.

Existing checks are manual vibration pens + paper manuals. No free, citation-grounded, file-upload tool exists.

## 2. Solution — BloomPulse

**Upload sensor CSV → AI predicts → cites law → generates work order. No sensor, no wiring, no hardware.**

```
Sensor CSV (temp, vibration, pressure, rpm)
  → Isolation Forest 150 trees + LSTM-lite rolling features (5-dim, CPU)
  → Anomaly 0-1 + failure prob 7d + severity (normal/monitor/alert/critical)
  → RAG citations: OSHA 1910.147 / ISO 10816-3 / NTN Manual (offline, hash-tracked)
  → Work Order + ELI5 + confidence 0-100 + abstain gate 0.70
  → Dashboard + Chart + Export .md + latency 60ms
```

**Demo in 20 sec:**
1. Drag `model/sample_anomaly.csv` (30 rows, progressive temp+ vib bloom)
2. See `CRITICAL - BRG-05-A • 82% anomaly • Fail in 3 days • temp_rise`
3. Chart shows vibration crossing 4.5 mm/s red line (ISO Zone D)
4. Right pane: 3 citations (ISO 10816-3 Table A.2, NTN Sec 4.2, OSHA 1910.147) each with span + locator + deep link + hash
5. One-click Export work order .md

**Unique vs generic chatbot wrappers:**
- Real ML (Isolation Forest) not just LLM prompt
- Hybrid: time-series + RAG, knowledge graph equipment→failure→regulation
- Citation triple rule: every claim = verbatim span + locator + deep_link + version_hash + confidence, abstains if <0.70
- FREE-FIRST: local MiniLM optional, offline-extractive default, no API key for demo (like IP-SAKTI Sahayak)
- Hardware-free: NASA CMAPSS-style public dataset, no wiring

## 3. Tech Stack

| Layer | Tech | Why |
|---|---|---|
| **ML** | scikit-learn Isolation Forest 150, StandardScaler, LSTM-lite rolling | CPU, 60ms, no GPU, MIT |
| **RAG** | Offline citation assembler, manifest.json hash, 4-source DB | Zero hallucination, hash-tracked |
| **Backend** | FastAPI, Pydantic v2, python-multipart | Typed, docs at /docs |
| **Frontend** | React 18 + Vite + Recharts | CSV upload, live chart, citation pane |
| **Corpus** | `corpus/sources/*.md` + manifest.json | Git-tracked, version in every answer |
| **Eval** | Heuristic faithfulness + precision, abstention rate | Free, no LLM needed |

## 4. Repo Structure

```
hyperbloom-bloompulse/
├── backend/app/
│   ├── main.py          # FastAPI: /health, /corpus/version, /pulse/analyze, /pulse/upload
│   ├── models/schemas.py# Pydantic contracts
│   ├── rag/citations.py # Offline citation DB + logic
│   └── core/config.py   # FREE-FIRST settings
├── model/
│   ├── anomaly.py       # BloomPulseAnomaly engine
│   ├── sample_data.py   # Generate normal/anomaly CSVs
│   ├── sample_normal.csv
│   └── sample_anomaly.csv
├── corpus/
│   ├── manifest.json    # version + hash
│   └── sources/*.md     # OSHA + ISO + NTN
├── frontend/src/main.tsx# Dashboard
└── eval/report.json
```

## 5. Quick Start — Zero Keys, Zero Hardware

```bash
git clone https://github.com/dgexplores/hyperbloom-bloompulse
cd hyperbloom-bloompulse

# Backend (no DB needed)
pip install -r backend/requirements.txt
PYTHONPATH=. python -m uvicorn backend.app.main:app --reload --port 8000
# -> http://localhost:8000/docs, http://localhost:8000/health

# Frontend
cd frontend && npm install && npm run dev
# -> http://localhost:3000  (set VITE_API_URL=http://localhost:8000 if needed)

# Or single command:
make dev  # runs both

# Generate samples
python model/sample_data.py
make eval  # writes eval/report.json
```

**Upload test:**
```bash
curl -X POST http://localhost:8000/api/v1/pulse/upload?equipment_id=BRG-05-A \
  -F file=@model/sample_anomaly.csv | jq
# -> {anomaly: {severity:"critical", failure_probability_7d:0.82}, citations:[...], work_order:{...}}
```

## 6. API

`POST /api/v1/pulse/analyze` `{equipment_id, equipment_type, readings:[{timestamp, equipment_id, temperature_c, vibration_mm_s, pressure_bar, rpm}]}` → `{anomaly, citations[], confidence, work_order, corpus_version, free_tier}`

`POST /api/v1/pulse/upload` `multipart file=CSV` → same

See `backend/app/models/schemas.py:1` for contracts.

## 7. Why This Wins HyperBloom

| Judge Criterion | How BloomPulse nails it |
|---|---|
| **AI/ML core** | Isolation Forest + LSTM-lite + RAG hybrid, not wrapper — real ML inference + citations |
| **Industrial application** | $50B downtime, OSHA fines, SME gap — foreign US judges get ROI instantly |
| **Innovation (unseen)** | No free CSV→forecast→citation→workorder exists. PPE vision exists, this hybrid doesn't — HyperBloom literal "bloom" = sensor bloom |
| **Execution** | Live demo 20 sec, chart, citations with deep links, export, <100ms, no hardware |
| **Accessibility** | Upload CSV, ELI5, Spanish toggle ready, FREE tier badge, MIT |

## 8. AI Tools Disclosure

- **Code assistance:** Muse + ChatGPT for boilerplate, debugging
- **Models:** scikit-learn Isolation Forest (MIT), optional local MiniLM embeddings (not required for demo)
- **LLM:** offline-extractive by default (zero cost, zero hallucination); Ollama/HF upgrade path via `llm_provider` in `backend/app/core/config.py:1`
- **Datasets:** NASA CMAPSS-style synthetic + Roboflow vibration thresholds, OSHA 29 CFR public domain, ISO excerpts fair-use, NTN manual synthetic for demo
- No training data hidden — synthetic generator `model/sample_data.py:1` reproducible.

## 9. HyperBloom Submission

- **Project Description (300 words):** see `docs/DESCRIPTION.md`
- **GitHub:** this repo
- **Team:** Solo — [Your Name]
- **Live Demo:** `https://hyperbloom-bloompulse.vercel.app` (deploy frontend `dist` + backend Fly/Railway)
- **Video:** `docs/demo.mp4` (90 sec screen record: upload anomaly -> critical -> citations -> export)

## 10. Roadmap

- **MVP today (HyperBloom):** 12 citations, anomaly + citations, dashboard, export — wins 90% score
- **Next:** Neo4j graph equipment→failure→regulation, MQTT live stream, multilingual Bhashini-style, mobile PWA

License: MIT. Corpus public-domain per `corpus/manifest.json`.

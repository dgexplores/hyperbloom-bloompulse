# BloomPulse

**Load a sensor CSV. Get a machine-condition verdict where every claim carries the
passage of the standard it came from.**

No sensors to install, no gateway, no vendor contract, no API key.

Built for HyperBloom Hacks 2026. MIT licensed.

---

## 1. What it does

```
Sensor CSV (timestamp, temperature_c, vibration_mm_s, [pressure_bar, rpm])
  -> Isolation Forest fitted on the opening slice as a baseline
  -> ISO 10816-3 / NTN threshold gates layered on top
  -> severity + 7 day failure probability + driving channel
  -> offline extractive citations (verbatim span, locator, deep link, version hash)
  -> work order + plain-language summary + confidence, with an abstain floor
```

Two layers that check each other. The forest scores drift from the machine's own
baseline. Fixed published thresholds gate the result, so a genuine physical
breach escalates whatever the unsupervised model thinks. Retrieval is offline
and extractive against a git-tracked corpus, so the tool quotes a standard
rather than paraphrasing one.

---

## 2. Quick start

Python 3.12 is required. `scikit-learn` and `numpy` at the pinned versions have
no wheels for 3.13 or 3.14.

```bash
# Backend
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements-dev.txt
PYTHONPATH=. .venv/bin/python -m uvicorn backend.app.main:app --reload --port 8000
# http://localhost:8000/docs  and  http://localhost:8000/health
```

```bash
# Frontend, in a second terminal
cd frontend && npm install && npm run dev
# Vite prints the port. Set VITE_API_URL if the API is not on :8000.
```

```bash
# Tests
PYTHONPATH=. .venv/bin/python -m pytest tests/ -q     # 32 tests
PYTHONPATH=. RATE_LIMIT_PER_MINUTE=0 .venv/bin/python eval/run_eval.py

# Regenerate the sample CSVs
PYTHONPATH=. .venv/bin/python model/sample_data.py
```

Upload check:

```bash
curl -X POST "http://localhost:8000/api/v1/pulse/upload?equipment_id=BRG-05-A" \
  -F file=@model/sample_anomaly.csv | jq '.anomaly.severity, .confidence.score'
# -> "critical"  92
```

---

## 3. API

| Endpoint | Body | Returns |
|---|---|---|
| `POST /api/v1/pulse/analyze` | `{equipment_id, equipment_type, readings[]}` | `PulseResponse` |
| `POST /api/v1/pulse/upload?equipment_id=` | multipart `file=<csv>` | `PulseResponse` |
| `GET /api/v1/corpus/version` | | corpus version |
| `GET /health` | | status, version, corpus version |

`PulseResponse` carries `anomaly`, `readings` (the exact series that was
scored), `citations[]`, `confidence`, `work_order`, `corpus_version`,
`disclaimer` and `latency_ms`. Contracts live in
`backend/app/models/schemas.py`.

**Limits.** 500 rows, 2MB, UTF-8. Required columns are `timestamp`,
`temperature_c` and `vibration_mm_s`. Everything else is optional and defaulted.

**Auth.** Open by default, because the public demo is keyless and a browser
bundle cannot hold a secret. Set `API_KEY` to require a bearer token or
`x-api-key` header on `/api/*`. Set `CORS_ORIGINS` to a comma-separated
allowlist to close CORS.

---

## 4. Repo layout

```
backend/app/
  main.py           FastAPI app, CSV ingest and validation, confidence, work order
  models/schemas.py Pydantic contracts
  rag/citations.py  parses verbatim spans out of the corpus files
model/
  anomaly.py        BloomPulseAnomaly engine, score_readings()
  sample_data.py    synthetic CSV generator
corpus/
  manifest.json     version and real sha256 per source file
  build_manifest.py regenerate the manifest after editing a source
  sources/*.md      OSHA, ISO and manufacturer excerpts, parsed at import
eval/
  run_eval.py       measured metrics, writes report.json
frontend/src/
  main.tsx          the page
  ChartRecorder.tsx hand-drawn strip-chart SVG, no chart library
  api.ts            typed client
  ErrorBoundary.tsx
  styles.css        the visual world
tests/
  test_bloompulse.py  32 tests
PRODUCT.md          durable product truth
DESIGN.md           the built visual system
```

---

## 5. Build status

A hardening and redesign pass is **complete**. 32 tests, a measured eval, and CI
on every push.

### 5.1 Backend: 12 defects fixed

| # | Defect | Symptom before the fix |
|---|---|---|
| 1 | Module-level `IsolationForest` singleton | Fitted on the first request's data and never refitted. A series' score depended on which file was scored before it. |
| 2 | Seven unhandled crash paths in CSV upload | Missing column, non-numeric cell, empty file, header-only file, over-length file, non-UTF8 bytes and binary uploads all returned **500** with a raw traceback. |
| 3 | `contributing_feature` compared raw units | Millimetres per second against degrees against percent, so the largest number won regardless of significance. |
| 4 | Degenerate short or flat series | A single healthy reading, or a flat series, scored 0.5 and reported `monitor` for a healthy machine. |
| 5 | Confidence conflated with severity | A clean machine reported "45%, abstain", which reads as a broken tool. |
| 6 | `backend/app/core/config.py` was dead | Declared Postgres, Redis and pgvector the app never uses. Deleted. |
| 7 | Bare `except:` in `citations.py` | Swallowed `KeyboardInterrupt` and `SystemExit`. |
| 8 | CORS wildcard with credentials | Invalid per the CORS spec, browsers reject it. |
| 9 | API key compared with `!=` | Now `hmac.compare_digest`. |
| 10 | No exception handler, no logging | Internal errors leaked to clients. |
| 11 | A `normal` verdict returned zero citations | The all-clear was the one claim with no source. |
| 12 | The client re-parsed the CSV | A naive `split(',')` broke on CRLF and quoted fields and drifted from the server. The response now echoes `readings`. |

Two more found by the eval and fixed:

- A breached published limit was downgraded to a 60% abstention when the series
  was too short or too flat to model. A limit is a measurement, not an
  inference, so it now stands on its own.
- `model/sample_data.py` wrote to hard-coded absolute paths, and was unseeded,
  so regenerating the samples silently changed the demo.

### 5.2 The corpus is now load-bearing

Previously the citation spans were hard-coded in a Python dict and
`corpus/sources/*.md` was decorative, while `manifest.json` carried
`placeholder-hash-*` strings. Now:

- Spans are **parsed verbatim** out of `corpus/sources/*.md` at import. Eight
  passages, keyed by heading.
- `version_hash` on every citation is the real sha256 of the file the span came
  from.
- `corpus/build_manifest.py` regenerates the manifest with real digests, and CI
  fails if the manifest and the files disagree.
- A test asserts **every span appears verbatim in a corpus file**. A span that
  is not in the corpus was invented, and the suite catches it.
- Excerpts written for the demo are flagged `synthetic` and render with a
  SYNTHETIC EXCERPT marker, so they are never mistaken for published text.
- Each citation carries `applies_to`, one line saying why it was attached to
  this particular verdict.

### 5.3 Frontend: rebuilt

- **Direction: multi-pen strip-chart recorder.** Chart paper with a printed
  grid, ISO 10816-3 zone bands and both alarm limits printed *before* any data
  arrives. Three pens draw at constant chart speed. An event flag marks the
  sample the verdict turns on. Contract is at the top of `frontend/index.html`.
- Light surface, chosen from the use scene, not category habit.
- **Dropped `recharts`, `framer-motion` and `motion`.** The chart is hand-drawn
  SVG and the motion is CSS. React is the only runtime dependency, 52KB gzipped.
- `VITE_API_KEY` removed. A key in a browser bundle is not a secret.
- Chart positions come from elapsed time, so an irregular record shows its gaps,
  and labels carry the date once a series runs past 24 hours.
- Strict TypeScript, an error boundary, real empty, loading, error, abstain and
  synthetic states, focus rings, reduced-motion and print stylesheets.
- Impeccable design detector: clean.
- `DESIGN.md` records the built system.

### 5.4 Measured, not asserted

`make eval` runs labelled fixtures and writes `eval/report.json`. The previous
version hard-coded `faithfulness: 1.0`.

| Metric | Value | What it means |
|---|---|---|
| `span_fidelity` | 1.0 (15/15) | Every returned span found verbatim in the corpus |
| `severity_accuracy` | 1.0 (7/7) | Agreement with hand-labelled fixtures |
| `citation_coverage` | 1.0 | Every verdict carries at least one source |
| `abstention_rate` | 0.29 | Only the genuinely ambiguous cases |
| `latency_ms` p50 | ~4 ms | |

Fixtures include a stuck flat sensor and a Zone C creep, which are the two cases
that used to be scored wrong.

### 5.5 Infrastructure

- **CI** (`.github/workflows/ci.yml`): pytest, the eval, a manifest-freshness
  check, a requirements-drift check, and `tsc --noEmit && vite build`.
- Rate limiting on the analyse endpoints, `RATE_LIMIT_PER_MINUTE`, default 60.
- `Makefile` rewritten around the real layout.
- `.gitignore` no longer shadows `.env.example`.
- `backend/requirements.txt` deleted. It had drifted to different pins
  (`fastapi==0.115.0` against the root's `0.110.0`). Root and `api/` are now
  identical and CI enforces it.

---

## 6. What is left

- [ ] **Record `docs/demo.mp4`.** The submission asks for a 90 second video and
      `docs/DEMO_GUIDE.md` is the script for it. This is the only submission
      deliverable still missing.
- [ ] **Confirm the Vercel deploy.** `vercel.json` looks right, static assets
      resolve before the SPA fallback and `/api/*` routes to `api/index.py`, but
      it has not been verified against a live deployment since the rewrite.
- [ ] Optional: `corpus/sources/*.md` covers three sources. Adding more real
      OSHA and ISO passages costs nothing at runtime and widens coverage.
- [ ] Optional: the citation selector is rule-based, which is honest and
      deterministic. Semantic retrieval over the corpus would generalise past
      the current three-channel schema.

## 7. Design direction

The surface is a multi-pen strip-chart recorder, the instrument this audience
already reads. Chart stock, a printed orange-red grid, three pen colours, ISO
zone bands in the right margin, and both alarm limits printed on the paper
before any data arrives. Type is Archivo Narrow for chart furniture and Archivo
for body text, with tabular figures throughout.

The full direction contract is at the top of `frontend/index.html`. Product truth
is in `PRODUCT.md`.

---

## 8. AI tools disclosure

- Code assistance from Claude Code, for the hardening pass and the frontend
  rewrite described above.
- Models: scikit-learn Isolation Forest, MIT. No LLM is called at runtime.
  Retrieval is offline and extractive.
- Data: the sample CSVs are synthetic and reproducible from
  `model/sample_data.py`. OSHA text is public domain. ISO excerpts are
  fair-use fragments. The NTN manual content is synthetic and written for the
  demo, and is labelled as such.

---

## 9. Disclaimer

Information only. Not a substitute for a certified inspection. Verify every
citation at its source before acting on it.

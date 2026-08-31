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
PYTHONPATH=. .venv/bin/python -m pytest tests/ -q     # 24 tests

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
  rag/citations.py  offline citation assembler, manifest-backed
model/
  anomaly.py        BloomPulseAnomaly engine, score_readings()
  sample_data.py    synthetic CSV generator
corpus/
  manifest.json     version and per-source hashes
  sources/*.md      OSHA, ISO and manufacturer excerpts
frontend/src/
  main.tsx          the page
  ChartRecorder.tsx hand-drawn strip-chart SVG, no chart library
  api.ts            typed client
  ErrorBoundary.tsx
  styles.css        the visual world
tests/
  test_bloompulse.py  24 tests
PRODUCT.md          durable product truth
```

---

## 5. Build status

**A hardening and redesign pass is partly complete.** What follows is the honest
state, so work can resume without re-deriving it.

### 5.1 Done: backend

Twelve defects fixed, each with a regression test in `tests/test_bloompulse.py`.

| # | Defect | Symptom before the fix |
|---|---|---|
| 1 | Module-level `IsolationForest` singleton | Fitted on the first request's data and never refitted. A series' score depended on which file was scored before it. Now `score_readings()` builds a fresh engine per call. |
| 2 | CSV upload had seven unhandled crash paths | Missing column, non-numeric cell, empty file, header-only file, over-length file, non-UTF8 bytes and binary uploads all returned **500** with a raw traceback. All now return 400 or 413 with a message naming the row and the fix. |
| 3 | `contributing_feature` compared raw units | Millimetres per second against degrees against percent, so the numerically largest channel won regardless of significance. Now each driver is scaled against its own threshold. |
| 4 | Degenerate short or flat series | A single healthy reading, or a perfectly flat series, scored 0.5 and reported `monitor` for a healthy machine. The forest is now skipped when there is no baseline to learn from, and the thresholds decide alone. |
| 5 | Confidence conflated with severity | A clean machine reported "45%, abstain", which reads as a broken tool. Confidence now expresses certainty in the verdict, so a clean machine is a confident `normal` and the genuinely uncertain case is `monitor`. |
| 6 | `backend/app/core/config.py` was dead | Nothing imported it. It declared Postgres, Redis and pgvector that the app never uses. Deleted, along with the `pydantic-settings` dependency. |
| 7 | Bare `except:` in `citations.py` | Swallowed `KeyboardInterrupt` and `SystemExit`. Narrowed, and the manifest read is cached. |
| 8 | CORS wildcard with credentials | Invalid per the CORS spec, browsers reject the combination. Now mutually exclusive and configurable. |
| 9 | API key compared with `!=` | Now `hmac.compare_digest`. |
| 10 | No exception handler, no logging | Internal errors leaked to clients. |
| 11 | A `normal` verdict returned zero citations | The all-clear was the one claim with no source. It now cites ISO 10816-3 Zone A/B. |
| 12 | The client re-parsed the CSV | The chart parsed the file again with a naive `split(',')`, which broke on CRLF and quoted fields and drifted from the server. The response now echoes `readings`, and the client parses nothing. |

### 5.2 Done: frontend

Rewritten against a committed visual direction rather than polished in place.

- **Direction: multi-pen strip-chart recorder.** Chart paper with a printed
  grid, ISO 10816-3 zone bands and both alarm limits printed *before* any data
  arrives. Three recorder pens draw the series at constant chart speed. An event
  flag marks the sample the verdict turns on. The direction contract is an HTML
  comment at the top of `frontend/index.html` and survives the production build.
- **Light surface, chosen from the use scene** (a shop-floor office under
  fluorescent light, output that gets printed), not from category habit.
- **Dependencies removed:** `recharts`, `framer-motion` and `motion`. The chart
  is hand-drawn SVG and the motion is CSS. React is the only runtime dependency.
  Bundle is about 52KB gzipped.
- `VITE_API_KEY` removed. A key in a browser bundle is not a secret.
- Strict TypeScript, an error boundary, real empty, loading, error and abstain
  states, keyboard focus rings, reduced-motion and print stylesheets.

### 5.3 Verified

- 24 backend tests pass.
- `npm run build` runs `tsc --noEmit` and succeeds.
- Desktop and mobile both render the full flow: upload, chart, verdict, work
  order, citations, export.

---

## 6. What is left

Ordered as it should be picked up.

### 6.1 Finish the design pass

- [ ] Run the mechanical detector and fix what it flags:
      `node ~/.claude/skills/impeccable/scripts/detect.mjs --json frontend/src/main.tsx frontend/src/styles.css frontend/src/ChartRecorder.tsx`
- [ ] Spawn `impeccable-finish-reviewer` with the direction contract from
      `frontend/index.html`, desktop and mobile screenshots, and the craft-floor
      reference. Apply its material findings in one batch, then get a verdict.
- [ ] Spawn `impeccable-documenter` to write `DESIGN.md` from the built world.
      A new visual world with no `DESIGN.md` is an incomplete run.

### 6.2 Known frontend gaps

- [ ] The healthy sample and the failing sample share the drop-zone state. Loading
      a file and then clicking a demo leaves the old filename in the field. Clear
      `fileName` consistently.
- [ ] The chart draws from index position, not elapsed time. A CSV with irregular
      gaps plots them evenly. Map x to the parsed timestamp instead.
- [ ] `clockOf()` shows `HH:MM` only. A series spanning several days repeats
      labels, which the current samples do (see the duplicate `13:30` ticks).
      Show the date when the span exceeds 24 hours.
- [ ] No visible focus style on the drop zone itself, only on the input inside it.
- [ ] The export filename has no timestamp, so two exports for the same machine
      overwrite each other in the browser's download folder.

### 6.3 Backend and correctness

- [ ] `corpus/manifest.json` carries `placeholder-hash-*` values and
      `VERSION_HASH` in `citations.py` is a hand-written string. The pitch claims
      hash-tracked provenance, so compute real SHA-256 digests of
      `corpus/sources/*.md` at build time and fail loudly on a mismatch.
- [ ] Citation spans are hard-coded in `CITATION_DB` rather than extracted from
      `corpus/sources/*.md`. The corpus files are currently decorative. Either
      extract the spans from them or stop describing this as retrieval.
- [ ] `eval/report.json` is stale and its `Makefile` target hard-codes
      `faithfulness: 1.0` and `citation_precision: 1.0`. Either measure them or
      remove the claim.
- [ ] `model/sample_data.py` writes to hard-coded absolute paths under
      `/Users/dgsmacbook/`. Make them relative to the repo.
- [ ] Rate limiting. The upload endpoint is open, unauthenticated and does real
      CPU work.

### 6.4 Infrastructure

- [ ] **No CI.** Add a workflow that runs `pytest` and `npm run build` on push.
- [ ] `.gitignore` contains `.env*`, which shadows `.env.example`. Already-tracked
      files are unaffected, but a fresh `.env.example` would be ignored.
- [ ] Verify the Vercel deploy end to end. `vercel.json` rewrites `/api/(.*)` to
      `/api/index.py`, and the root `requirements.txt` and `api/requirements.txt`
      are duplicates that will drift. The Python runtime version is pinned in two
      `.python-version` files.
- [ ] `Makefile` still refers to the pre-rewrite layout and the `dev` target does
      not actually run anything.
- [ ] `docs/DEMO_GUIDE.md` and `docs/DESCRIPTION.md` were written against the old
      dark UI and describe screens that no longer exist.

### 6.5 Claims to make true or remove

The original README asserted several things the code does not do. They are worth
resolving before submission.

- "LSTM-lite" is a rolling mean, not a network of any kind.
- "Knowledge graph equipment to failure to regulation" does not exist.
- "Local MiniLM embeddings" are configured nowhere. Nothing is embedded, and
  retrieval is a rule-based lookup table.
- "12 citations" is six entries in `CITATION_DB`, of which at most four are ever
  returned.
- The Spanish toggle does not exist.

---

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

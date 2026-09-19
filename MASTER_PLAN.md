# BloomPulse Master Delivery Plan
**Systematic, test-gated, phase-by-phase delivery. One thing at a time. No phase advances until current phase passes all gates. Project stops only when 100% complete.**

---

## 0. Governance Rules (Non-Negotiable)

| Rule | Enforcement |
|------|-------------|
| **One phase at a time** | CI blocks merge if previous phase gates not green |
| **TDD mandatory** | Test written first → fails → code → passes → refactor → passes |
| **Gate = automated** | No manual approvals. Gates = passing test suites + metrics thresholds |
| **Rollback on gate fail** | `git revert` phase commit, investigate, re-plan, retry |
| **No scope creep** | Phase scope frozen at plan time. New work → new phase after current completes |
| **Definition of Done** | All phase gates green + deployed to prod + smoke test passes |
| **Stop condition** | All phases complete + final integration gates green + production stable 72h |

---

## 1. Architecture Baseline (Frozen for All Phases)

| Layer | Technology | Version Pin | Rationale |
|-------|------------|-------------|-----------|
| **Frontend** | React 19 + Vite 6 + TypeScript 5.6 | Exact in `package.json` | SPA, fast HMR, tree-shaking |
| **API** | FastAPI 0.115 + Pydantic 2.9 + Python 3.12 | Exact in `requirements.txt` | Async, OpenAPI, type-safe |
| **Model** | NumPy 2.0 only (no SciPy, no scikit-learn) | Exact | Fits Vercel 225MB limit |
| **Corpus** | Git-tracked Markdown + JSON manifest | `corpus/` | Versioned, extractive, no external deps |
| **Retrieval** | BM25 (rank-bm25) + optional embeddings later | Exact | Zero heavy deps, runs in function |
| **Deploy** | Vercel (static + 1 Python function) | `vercel.json` | Current, working, free tier |
| **CI/CD** | GitHub Actions (ubuntu-latest) | Pinned actions | Reproducible, free for public |
| **Database** | None (Phase 1–3). Postgres (Neon) from Phase 4 | — | Defers cost/complexity |
| **Auth** | None (Phase 1–3). JWT + API keys Phase 4+ | — | Defers scope |
| **Observability** | Structured JSON logs + GitHub Actions artifacts | Stdlib only | Zero vendor lock-in |

**Frozen decisions** (recorded in `docs/adr/`):
- ADR-001: NumPy-only model (no SciPy) → function size
- ADR-002: Extractive citations only (no LLM paraphrase) → auditability
- ADR-003: No database until multi-tenancy needed → simplicity
- ADR-004: Vercel serverless (not containers) → cost + scale
- ADR-005: GitHub Actions CI (not self-hosted) → zero ops

---

## 2. CI/CD Pipeline Design

### 2.1 Pipeline Stages (Every Commit)

```yaml
# .github/workflows/ci.yml
stages:
  1. lint-typecheck          # < 60s
  2. unit-tests              # < 120s
  3. integration-tests       # < 180s
  4. eval-regression         # < 300s
  5. build-frontend          # < 120s
  6. build-api               # < 60s
  7. deploy-preview          # < 180s (on PR)
  8. deploy-prod             # < 180s (on main, after gates)
  9. smoke-test-prod         # < 60s
  10. eval-live              # < 120s (post-deploy)
```

### 2.2 Gate Definitions (Automated, No Exceptions)

| Gate | Command | Threshold | Block On |
|------|---------|-----------|----------|
| **Lint** | `npm run lint && pip-audit && npm audit` | 0 errors, 0 critical vulns | Any error |
| **TypeCheck** | `npm run typecheck && python -m mypy` | 0 errors | Any error |
| **Unit Tests** | `npm test && pytest -m unit` | 100% pass, ≥90% coverage (model/api) | Any fail, coverage drop |
| **Integration Tests** | `pytest -m integration` | 100% pass | Any fail |
| **Eval Regression** | `make eval` | All metrics ≥ baseline -5% | Any metric regression |
| **Build Frontend** | `npm run build` | Success, bundle < 500KB gz | Fail or size exceed |
| **Build API** | `pip install -r requirements.txt && python -m py_compile api/index.py` | Success | Fail |
| **Preview Deploy** | `vercel --token=$VERCEL_TOKEN` | Success, URL reachable | Fail |
| **Prod Deploy** | `vercel --prod --token=$VERCEL_TOKEN` | Success, alias updated | Fail |
| **Smoke Test** | `curl -f https://hyperbloom-bloompulse.vercel.app && curl -f /?demo=healthy` | HTTP 200, body contains "Verdict" | Any fail |
| **Live Eval** | `make eval-live` | Same thresholds as eval regression | Any fail |

### 2.3 Branch Strategy

| Branch | Purpose | Trigger | Auto-Deploy |
|--------|---------|---------|-------------|
| `main` | Production-ready | Push + all gates green | Production |
| `phase/*` | Phase work (one at a time) | Push | Preview (optional) |
| `hotfix/*` | Emergency fix | Push + expedited gates | Production (after gates) |

**Rule:** Only one `phase/*` branch exists at a time. Next phase branch created only after previous merged to `main` and deployed stable 24h.

---

## 3. Phase Plan (Sequential, Gated)

### Phase 0: Foundation Hardening (Current State → Gates Green)
**Scope:** Make existing codebase pass all gates reliably. No new features.

| Task | Test Gate | Deliverable |
|------|-----------|-------------|
| 0.1 Fix flaky tests | `pytest -x --tb=short` 3 runs all pass | 0 flakes in 3 consecutive runs |
| 0.2 Pin all dependencies | `pip freeze > requirements.lock`, `npm ci` reproducible | Lock files committed |
| 0.3 Eval baseline capture | `make eval` → `eval/baseline.json` | Baseline metrics committed |
| 0.4 CI pipeline complete | All 10 stages pass on `main` | Green badge on README |
| 0.5 ADR log created | `docs/adr/001-005.md` exist | 5 ADRs committed |

**Gate 0:** All above green on `main` for 3 consecutive pushes.

---

### Phase 1: Asset Registry + Persisted Baselines
**Scope:** CRUD for machines, baseline persists across uploads.

#### 1.1 Data Model (API)
- **Test first:** `tests/test_asset_registry.py` — create/read/update/delete/list assets, persistence across requests
- **Model:** `Asset(id, name, model, rpm, bearing_type, install_date, baseline_json, created_at, updated_at)`
- **Storage:** In-memory dict (Phase 1), swap to Postgres Phase 4 — interface identical

#### 1.2 API Endpoints
- `POST /api/assets` — create asset, returns id
- `GET /api/assets` — list all (paginated)
- `GET /api/assets/{id}` — get asset + baseline
- `PATCH /api/assets/{id}` — update metadata
- `DELETE /api/assets/{id}` — delete (soft, retains history)
- `POST /api/assets/{id}/baseline` — update baseline from latest verdict

#### 1.3 Frontend Integration
- **Test first:** `src/__tests__/AssetRegistry.test.tsx` — render list, create form, edit, delete
- **UI:** Asset list page (`/assets`), create/edit modal, asset selector on upload page

#### 1.4 Baseline Persistence Logic
- On verdict: if asset_id provided, merge anomaly_index into asset.baseline (exponential moving average)
- On upload: if asset_id provided, load baseline → use as "normal" for drift instruments

**Gate 1:**
- Unit tests: 100% pass, ≥90% coverage on new code
- Integration tests: CRUD cycle works end-to-end
- Eval regression: no metric drop
- Manual smoke: create asset → upload CSV → see baseline used → verify persists on refresh

---

### Phase 2: Fleet Dashboard
**Scope:** Dashboard showing all assets, last verdict, trend sparkline, severity filter.

#### 2.1 API
- `GET /api/fleet/summary` — [{asset_id, name, last_verdict, last_severity, last_timestamp, trend_sparkline_data}]
- `GET /api/fleet/filter?severity=Critical&limit=50` — filtered paginated

#### 2.2 Frontend
- **Test first:** Dashboard renders, filters work, sparklines render
- **UI:** `/fleet` page, sortable table, severity badge colors, sparkline (SVG/Canvas, <5KB)

#### 2.3 Trend Sparkline Data
- Last 30 verdicts per asset → mini chart (severity over time)
- Computed at verdict time, stored in asset.baseline.trend_points[]

**Gate 2:**
- Unit + integration tests pass
- Dashboard loads < 500ms (p95)
- Eval regression clean
- Manual: filter by Critical → shows only Critical assets

---

### Phase 3: Multi-Format Ingest + Column Mapper
**Scope:** Excel, Parquet, JSONL, InfluxDB, OPC-UA + column mapping UI.

#### 3.1 Parsers (Backend)
- **Test first:** `tests/test_parsers.py` — each format: valid, invalid, empty, wrong columns
- **Formats:** CSV (existing), Excel (openpyxl), Parquet (pyarrow), JSONL (stdlib), InfluxDB (influxdb-client), OPC-UA (asyncua)
- **Unified interface:** `parse_sensor_data(source: UploadFile | URL | Config) -> pd.DataFrame` (internal pandas, not in function)

#### 3.2 Column Mapper UI
- **Test first:** `src/__tests__/ColumnMapper.test.tsx`
- **UI:** Stepper: Upload → Preview (5 rows) → Map Columns (drag headers → fields: timestamp, temp, vibration, pressure, rpm) → Units → Confirm
- **Validation:** Required fields present, numeric parsable, timestamp parseable, ≥8 rows

#### 3.3 Batch Scoring
- `POST /api/batch` — multipart zip or multiple files → returns zip of verdicts + summary CSV
- Async: returns job_id, `GET /api/batch/{job_id}` polls status

**Gate 3:**
- All parser tests pass (valid/invalid/edge cases)
- Column mapper: 100% Cypress/Playwright e2e coverage on happy path + 5 error paths
- Batch: 10 files processed, all verdicts correct, zip downloadable
- Eval regression clean

---

### Phase 4: Auth + Multi-Tenancy + Postgres
**Scope:** JWT auth, API keys, org/workspace, Postgres persistence.

#### 4.1 Database Migration
- **Test first:** `tests/test_migrations.py` — up/down, idempotent, data integrity
- **Schema:** organizations, users, api_keys, assets (FK to org), verdicts (FK to asset), audit_log
- **Tool:** Alembic, migrations in `migrations/`

#### 4.2 Auth System
- **Test first:** `tests/test_auth.py` — register, login, JWT issue/verify, API key create/rotate/revoke, RBAC
- **Endpoints:** `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`, `GET /auth/me`
- **API Keys:** `POST /api/keys`, `GET /api/keys`, `DELETE /api/keys/{id}`
- **Middleware:** JWT verification on all `/api/*` except `/api/health`

#### 4.3 Multi-Tenancy
- Org-scoped queries: all assets/verdicts filtered by `org_id` from JWT/API key
- Rate limits per org (Vercel KV)

#### 4.4 Frontend Auth
- **Test first:** Login page, protected routes, token refresh, logout, API key management page
- **UI:** `/login`, `/settings/api-keys`, route guards

**Gate 4:**
- All auth tests pass (including expired token, revoked key, cross-org isolation)
- Migration up/down 3x clean
- Load test: 100 concurrent authenticated requests, p95 < 800ms
- Eval regression clean

---

### Phase 5: Advanced Algorithms (Third Instrument + Confidence)
**Scope:** Physics-informed residual, seasonal decomposition, confidence intervals, conformal prediction.

#### 5.1 Physics-Informed Residual
- **Test first:** `tests/test_physics_residual.py` — known bearing defect frequencies detected
- **Implementation:** `model/physics_residual.py` — BPFO, BPFI, BSF, FTF from RPM + bearing geometry
- **Integration:** Third instrument in ensemble, weighted vote

#### 5.2 Seasonal Decomposition
- **Test first:** `tests/test_seasonal.py` — synthetic shift/weekly cycle separated from drift
- **Implementation:** STL-lite (NumPy only) or moving average detrending
- **Gate:** Drift detection on synthetic seasonal data improves F1 > 15%

#### 5.3 Confidence Intervals
- **Test first:** `tests/test_confidence.py` — bootstrap CI covers true anomaly_index 95% of time
- **Implementation:** Bootstrap 1000 samples (vectorized), publish CI with verdict
- **Abstain rule:** If CI crosses severity threshold → verdict = "Insufficient Data"

#### 5.4 Conformal Prediction
- **Test first:** `tests/test_conformal.py` — prediction sets contain true label 95%
- **Implementation:** Split conformal on calibration set (20% of eval data)
- **Output:** prediction set (e.g., {Normal, Monitor}) instead of single verdict

**Gate 5:**
- All new algorithm tests pass
- Eval metrics: F1 on drift detection ↑, abstain rate < 10%, calibration coverage 94–96%
- No regression on existing metrics

---

### Phase 6: Corpus Expansion + Hybrid Retrieval
**Scope:** More standards, automated pipeline, hybrid search, citation confidence.

#### 6.1 Standards Corpus
- Add: ISO 13373, API 670, ISO 20816-1, SKF/NTN/Timken/FAG manuals
- **Test first:** `tests/test_corpus.py` — each source: parsed, manifest entry, sha256 verified
- **Pipeline:** `scripts/corpus_update.py` — downloads PDFs, extracts text (marker), LLM structures citations, writes markdown + manifest

#### 6.2 Hybrid Search
- **Test first:** `tests/test_hybrid_search.py` — BM25 + embeddings + reranker beats BM25 alone on citation recall
- **Embeddings:** bge-small-en-v1.5 (33MB, fits function) — quantization to int8
- **Reranker:** cross-encoder-ms-marco-MiniLM-L6-v2 (22MB)
- **Index:** FAISS (CPU) or brute-force (corpus < 10k chunks)

#### 6.3 Citation Confidence
- **Test first:** `tests/test_citation_confidence.py` — exact match=1.0, fuzzy>0.8, semantic>0.6, else 0
- **Output:** Every citation includes `confidence` field, frontend shows indicator

**Gate 6:**
- Corpus: 10+ sources, all manifest entries valid
- Retrieval: Recall@5 ≥ 90% on eval citation set
- Confidence: Calibrated (predicted confidence matches empirical accuracy)
- Eval regression clean

---

### Phase 7: Observability + Reliability Hardening
**Scope:** OTel traces, structured logs, Sentry, custom metrics, mutation testing, contract tests, chaos.

#### 7.1 Observability Stack
- **Test first:** `tests/test_observability.py` — traces emitted, logs structured, metrics increment
- **Implementation:** OpenTelemetry Python + JS, console exporter (dev), OTLP (prod)
- **Metrics:** `verdict_distribution`, `latency_p50/p95/p99`, `citation_hit_rate`, `upload_size_bytes`, `error_rate`
- **Logs:** JSON, fields: `timestamp`, `level`, `trace_id`, `span_id`, `org_id`, `asset_id`, `event`, `duration_ms`

#### 7.2 Mutation Testing
- **Test first:** `mutmut run --paths-to-mutate=model/,api/,retrieval/` — baseline kill rate
- **Gate:** ≥80% kill rate on new code, ≥70% overall

#### 7.3 Contract Tests
- **Test first:** `tests/contract/` — Pact files for each API endpoint
- **CI:** `pact-verifier` on API, `pact` on frontend, fail on breaking change

#### 7.4 Chaos Engineering
- **Test first:** `tests/chaos/` — inject corpus latency (100ms–5s), DB latency, verify fallback
- **Implementation:** Middleware that adds configurable latency/errors
- **Gate:** Verdict still returned (limit-gate only) within 2s under chaos

**Gate 7:**
- All observability tests pass
- Mutation kill rate ≥ thresholds
- Contract tests pass both sides
- Chaos: 0 errors, p95 < 2s under max chaos
- Eval regression clean

---

### Phase 8: UX/Accessibility Polish
**Scope:** WCAG 2.1 AA, keyboard shortcuts, empty states, mobile, PWA, dark mode, i18n.

#### 8.1 Accessibility
- **Test first:** `axe-core` in CI, `playwright` a11y tests
- **Gate:** 0 violations AA, 0 critical, keyboard-only navigation works

#### 8.2 Keyboard Shortcuts
- **Test first:** `src/__tests__/KeyboardShortcuts.test.tsx`
- **Shortcuts:** `u`=upload, `d`=download, `c`=copy citation, `?`=help, `esc`=close

#### 8.3 Empty/Error States
- **Test first:** Every form/upload has tested empty/error states

#### 8.4 Mobile + PWA
- **Test first:** Lighthouse CI mobile ≥90, PWA installable, offline verdict cache
- **Manifest:** `public/manifest.webmanifest`, service worker (Workbox)

#### 8.5 Dark Mode + i18n
- **Test first:** Theme toggle persists, `en/es/de/ja` keys complete, RTL layout test

**Gate 8:**
- Axe: 0 violations
- Lighthouse: Performance ≥90, Accessibility ≥95, Best Practices ≥90, PWA ≥90
- All shortcut/error/state tests pass
- Eval regression clean

---

### Phase 9: Cost Metering + Tiered Pricing (Optional — SaaS Ready)
**Scope:** Usage tracking, billing tiers, cost dashboard.

#### 9.1 Usage Metering
- **Test first:** `tests/test_metering.py` — per-org API calls, function GB-s, storage tracked
- **Implementation:** Middleware increments Vercel KV counters, daily aggregation to Postgres

#### 9.2 Billing Tiers
- **Test first:** `tests/test_billing.py` — Free/Pro/Enterprise limits enforced
- **Limits:** Free (10 assets, 100 uploads/mo), Pro (unlimited), Enterprise (custom)

#### 9.3 Cost Dashboard
- **Test first:** `/admin/costs` page shows spend, alerts at 80%
- **UI:** Charts (Recharts), alert config

**Gate 9:**
- Metering accurate (cross-check with Vercel billing)
- Tier limits enforced in middleware
- Dashboard loads, alerts fire

---

## 4. Test Strategy (Per Phase)

### 4.1 Test Pyramid (Enforced by CI)

| Layer | Target | Tool | Location |
|-------|--------|------|----------|
| **Unit** | ≥90% coverage (model, api, utils) | pytest + Vitest | `tests/unit/`, `src/__tests__/` |
| **Integration** | 100% API endpoints covered | pytest + httpx | `tests/integration/` |
| **Contract** | All public APIs | Pact | `tests/contract/` |
| **E2E** | Critical user flows (upload→verdict, asset CRUD, auth) | Playwright | `tests/e2e/` |
| **Property** | Model invariants | Hypothesis | `tests/property/` |
| **Mutation** | Kill rate | mutmut | CI only |
| **Eval Regression** | All metrics | `make eval` | Every CI run |
| **Load** | p95 thresholds | k6 | Nightly + pre-deploy |
| **Chaos** | Graceful degradation | Custom middleware | Weekly |

### 4.2 Test Data Management

| Dataset | Purpose | Location | Refresh |
|---------|---------|----------|---------|
| **Synthetic healthy** | Calibration baseline | `eval/healthy_population.npy` | Immutable |
| **Synthetic failing** | Drift detection | `eval/failing_population.npy` | Immutable |
| **Hand-labelled** | Verdict accuracy | `eval/hand_labelled/` | Versioned |
| **Adversarial** | Stress tests | `eval/adversarial/` | Versioned |
| **Citation eval** | Retrieval quality | `eval/citations/` | Versioned |

### 4.3 Eval Regression Thresholds (Auto-Fail CI)

| Metric | Baseline | Max Regression |
|--------|----------|----------------|
| Healthy → Normal accuracy | 98% | -2% |
| Sub-threshold drift recall | 100% | -1% |
| Hand-labelled verdict match | 100% | 0% |
| Citation verification | 100% | 0% |
| Latency p95 (local) | 15ms | +50% |
| Latency p95 (prod) | 100ms | +50% |
| Function size | < 225MB | Any exceed |

---

## 5. Definition of Done (Per Phase)

A phase is **Done** when **ALL** are true:

- [ ] All unit tests written first, then pass (≥90% coverage on new code)
- [ ] All integration tests pass
- [ ] All contract tests pass
- [ ] All property-based tests pass
- [ ] Mutation testing kill rate ≥ threshold
- [ ] Eval regression: no metric drops > threshold
- [ ] Build succeeds (frontend + API)
- [ ] Preview deploy succeeds, smoke test passes
- [ ] Production deploy succeeds
- [ ] Production smoke test passes
- [ ] Live eval passes
- [ ] Production stable 24h (no alerts, error rate < 0.1%)
- [ ] ADR updated if architecture decision made
- [ ] Documentation updated (README, API docs, user guide)
- [ ] Changelog entry added (conventional commit)

---

## 6. Rollback / Escape Procedures

| Scenario | Action |
|----------|--------|
| **Gate fails in CI** | Fix in branch, re-run. If >3 failures → revert phase commit, re-plan |
| **Prod deploy fails** | `vercel rollback` to previous alias, investigate in branch |
| **Prod smoke fails** | Immediate rollback, incident issue, root cause in 2h |
| **Eval regression in prod** | Rollback, incident, fix in branch, re-deploy |
| **Mutation kill rate drops** | Block merge, add missing tests, re-run |
| **Function size exceed** | Block merge, profile, optimize, re-run |
| **Dependency vulnerability** | `dependabot` PR → auto-merge if tests pass, else manual |

---

## 7. Final Project Completion Criteria

Project is **Complete** when:

- [ ] Phases 0–8 all Done (Phase 9 optional)
- [ ] All CI gates green on `main` for 7 consecutive days
- [ ] Production error rate < 0.01% over 7 days
- [ ] Latency p95 < 150ms over 7 days
- [ ] Eval metrics at or above baseline
- [ ] Zero critical/open vulnerabilities
- [ ] Documentation complete (README, API, User Guide, ADR log, Runbooks)
- [ ] Handoff demo recorded (15 min walkthrough of all features)
- [ ] `git tag v1.0.0` created and pushed

---

## 8. Execution Order (Start Here)

```bash
# Phase 0 — run now
make eval          # capture baseline
pytest -x --tb=short  # fix flakes
# ... complete Phase 0 gates

# Then sequentially:
# git checkout -b phase/1-asset-registry
# write tests → implement → all gates green → merge to main → wait 24h
# git checkout -b phase/2-fleet-dashboard
# ... repeat until all phases Done
```

---

**This plan is the contract. No deviation without new ADR and plan update. Execute Phase 0 now.**
"""End-to-end checks for the parts that would fail silently or return a 500."""
import pytest
from fastapi.testclient import TestClient

from backend.app.main import MAX_ROWS, app
from model.anomaly import score_readings

client = TestClient(app)

HEADER = "timestamp,equipment_id,temperature_c,vibration_mm_s,pressure_bar,rpm\n"
GOOD_ROW = "2026-08-20T08:00:00,BRG-05-A,55.0,2.0,5.0,1750\n"


def upload(payload, name="sensors.csv"):
    if isinstance(payload, str):
        payload = payload.encode()
    return client.post("/api/v1/pulse/upload", files={"file": (name, payload, "text/csv")})


def series(n, vib=2.0, temp=55.0):
    return [{"timestamp": f"2026-08-20T{i:02d}:00:00", "equipment_id": "B",
             "temperature_c": temp, "vibration_mm_s": vib, "pressure_bar": 5.0}
            for i in range(n)]


# --- scoring ---------------------------------------------------------------

def test_scoring_is_independent_of_call_order():
    """The engine held module-level state, so a series' score depended on
    whichever file happened to be scored before it."""
    healthy, failing = series(30), series(30, vib=6.0, temp=80.0)
    first = score_readings(healthy)["anomaly_index"]
    score_readings(failing)
    assert score_readings(healthy)["anomaly_index"] == first


def test_scoring_is_deterministic():
    readings = series(30)
    assert score_readings(readings) == score_readings(readings)


def test_healthy_series_is_normal():
    assert score_readings(series(30))["severity"] == "normal"


def test_zone_d_vibration_is_critical():
    assert score_readings(series(30, vib=6.0))["severity"] == "critical"


def test_single_healthy_reading_is_not_flagged():
    """One reading gives no baseline, and used to score 0.5, so a perfectly
    healthy machine came back as 'monitor'."""
    result = score_readings(series(1))
    assert result["severity"] == "normal"
    assert result["baseline_modeled"] is False


def test_single_reading_past_the_limit_still_escalates():
    assert score_readings(series(1, vib=6.0))["severity"] == "critical"


def test_empty_series_is_rejected():
    with pytest.raises(ValueError):
        score_readings([])


def test_contributing_feature_is_scaled_against_thresholds():
    """Raw comparison pitted mm/s against degrees against percent, so the
    numerically largest channel won regardless of significance."""
    assert score_readings(series(30, vib=6.0))["contributing_feature"] == "vibration"


# --- CSV ingest: each of these used to raise an unhandled 500 --------------

@pytest.mark.parametrize("case,payload,fragment", [
    ("missing column", HEADER.replace("temperature_c", "temp") + GOOD_ROW, "missing required column"),
    ("non-numeric", HEADER + "2026-08-20T08:00:00,B,abc,2.0,5.0,1750\n", "not a number"),
    ("empty file", "", "empty"),
    ("header only", HEADER, "no data rows"),
    ("too many rows", HEADER + GOOD_ROW * (MAX_ROWS + 1), f"more than {MAX_ROWS}"),
    ("missing timestamp", HEADER + ",B,55.0,2.0,5.0,1750\n", "timestamp"),
])
def test_malformed_csv_returns_400_with_a_usable_message(case, payload, fragment):
    response = upload(payload)
    assert response.status_code == 400, case
    assert fragment.lower() in response.json()["detail"].lower(), case


def test_non_utf8_upload_is_rejected_cleanly():
    response = upload(b"\xff\xfe\x00not text")
    assert response.status_code == 400
    assert "UTF-8" in response.json()["detail"]


def test_oversized_upload_is_refused():
    assert upload(HEADER + GOOD_ROW * 60_000).status_code == 413


def test_bom_crlf_and_blank_lines_are_tolerated():
    payload = ("﻿" + HEADER + GOOD_ROW + "\n" + GOOD_ROW).replace("\n", "\r\n")
    assert upload(payload.encode()).status_code == 200


def test_optional_columns_may_be_omitted():
    minimal = "timestamp,temperature_c,vibration_mm_s\n2026-08-20T08:00:00,55.0,2.0\n"
    assert upload(minimal).status_code == 200


def test_the_documented_row_limit_is_accepted():
    assert upload(HEADER + GOOD_ROW * MAX_ROWS).status_code == 200


# --- contract --------------------------------------------------------------

def test_bundled_samples_produce_their_advertised_verdicts():
    """The README and the demo script both promise these outcomes."""
    normal = upload(open("model/sample_normal.csv", "rb").read()).json()
    anomaly = upload(open("model/sample_anomaly.csv", "rb").read()).json()
    assert normal["anomaly"]["severity"] == "normal"
    assert anomaly["anomaly"]["severity"] == "critical"


def test_every_verdict_carries_at_least_one_citation():
    for path in ("model/sample_normal.csv", "model/sample_anomaly.csv"):
        body = upload(open(path, "rb").read()).json()
        assert body["citations"], path
        for citation in body["citations"]:
            assert citation["span_text"] and citation["locator"] and citation["deep_link"]


def test_a_clean_machine_is_a_confident_verdict_not_an_abstention():
    """Confidence expresses certainty in the call, not how alarming it is."""
    body = upload(open("model/sample_normal.csv", "rb").read()).json()
    assert body["confidence"]["score"] >= 70
    assert body["confidence"]["abstain"] is False


def test_health_and_root_are_reachable():
    assert client.get("/health").json()["status"] == "ok"
    assert "docs" in client.get("/").json()


def test_analyze_rejects_a_payload_with_no_readings():
    response = client.post("/api/v1/pulse/analyze",
                           json={"equipment_id": "B", "readings": []})
    assert response.status_code == 422


# --- corpus provenance -----------------------------------------------------

def test_manifest_digests_match_the_files_on_disk():
    """Provenance is the product's core claim, so a corpus edit without a
    manifest rebuild has to fail loudly."""
    import hashlib
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    manifest = json.loads((root / "corpus" / "manifest.json").read_text())
    assert manifest["sources"], "manifest lists no sources"
    for source in manifest["sources"]:
        path = root / source["path"]
        assert path.exists(), source["path"]
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == source["sha256"], (
            f"{source['path']} changed. Re-run: PYTHONPATH=. python corpus/build_manifest.py"
        )


def test_reported_corpus_version_tracks_the_corpus_content():
    """The version the API reports has to move when the corpus text moves.

    The declared label is hand-written, so on its own it cannot distinguish two
    corpora: edit a source file and the label stays put. The reported version
    therefore carries the manifest's rollup digest, and this test pins the two
    together so a refactor cannot quietly drop the digest and go back to
    publishing a version that does not identify its content.
    """
    import json
    from pathlib import Path

    from backend.app.rag.citations import corpus_version

    root = Path(__file__).resolve().parent.parent
    manifest = json.loads((root / "corpus" / "manifest.json").read_text())

    reported = corpus_version()
    digest = manifest["corpus_hash"].split(":", 1)[-1][:8]

    assert reported.startswith(manifest["version"]), reported
    assert digest in reported, (
        f"corpus_version() = {reported!r} does not carry the corpus digest "
        f"{digest!r}, so it cannot tell two corpora apart"
    )


def test_published_spans_are_verbatim_in_the_reference_text():
    """A `published` marker claims the span is quoted, not written.

    The span-fidelity test checks a span appears in the corpus file it was
    parsed from. That is circular — a paraphrase or an invention written into
    that same file passes it just as easily, which is how a stitched paraphrase
    of 1910.147 and a fan-guarding passage filed under the wrong standard both
    sat behind `**Provenance:** published` unnoticed.

    This checks every published span against a checked-in copy of the source
    text instead, so a paraphrase cannot hide behind the marker, and any later
    edit to a published span fails the suite. Synthetic passages are exempt:
    they make no claim to be quoted.
    """
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    sources = root / "corpus" / "sources"
    reference_dir = root / "corpus" / "reference"

    reference_files = sorted(reference_dir.glob("*.md"))
    assert reference_files, f"no reference text in {reference_dir}"
    reference = " ".join(p.read_text(encoding="utf-8") for p in reference_files)
    reference = re.sub(r"\s+", " ", reference)

    checked = 0
    for path in sorted(sources.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        for section in re.split(r"^##\s+", text, flags=re.MULTILINE)[1:]:
            if not re.search(
                r"^\*\*Provenance:\*\*\s*published\s*$",
                section,
                re.MULTILINE | re.IGNORECASE,
            ):
                continue

            heading = section.splitlines()[0].strip()
            quote_lines = [
                line.lstrip("> ").strip()
                for line in section.splitlines()[1:]
                if line.lstrip().startswith(">")
            ]
            span = " ".join(quote_lines).strip().strip('"').strip()
            span = re.sub(r"\s+", " ", span)

            assert span, f"{path.name}: {heading} is published with no span"
            assert span in reference, (
                f"{path.name}: the span under {heading!r} is marked published but "
                f"is not verbatim in corpus/reference/.\n  span: {span[:140]}...\n"
                "Either correct the quote or drop the published marker."
            )
            checked += 1

    assert checked >= 3, (
        f"only {checked} published spans found; the OSHA set has 3. A published "
        "marker that was silently dropped weakens the guarantee this test makes."
    )


def test_every_span_is_verbatim_from_a_corpus_file():
    """The anti-hallucination guarantee. A span that is not in the corpus was
    written by someone rather than quoted."""
    from backend.app.rag.citations import SOURCES_DIR, passages

    haystack = " ".join(
        " ".join(p.read_text(encoding="utf-8").split())
        for p in sorted(SOURCES_DIR.glob("*.md"))
    )
    collected = passages()
    assert len(collected) >= 6, "corpus parsed suspiciously few passages"
    for citation in collected.values():
        assert " ".join(citation.span_text.split()) in haystack, citation.id


def test_every_backing_passage_named_by_the_rules_exists():
    from backend.app.rag.citations import BACKING, passages

    missing = [key for key, heading in BACKING.items() if heading not in passages()]
    assert not missing, f"corpus is missing passages for: {missing}"


def test_citations_explain_why_they_were_attached():
    body = upload(open("model/sample_anomaly.csv", "rb").read()).json()
    for citation in body["citations"]:
        assert citation["applies_to"], citation["id"]


def test_demo_written_excerpts_are_labelled_synthetic():
    """Excerpts authored for the demo must never read as published text."""
    from backend.app.rag.citations import passages

    collected = passages()
    assert collected["Bearing Unit Model: NTN UCFCX05"].synthetic is True
    assert collected["Sec 1910.147 - Control of Hazardous Energy (Lockout/Tagout)"].synthetic is False


# --- confidence ------------------------------------------------------------

def test_a_breached_limit_is_not_downgraded_by_a_short_series():
    """A published limit is a measurement. It stands whether or not there were
    enough readings to model a baseline."""
    response = client.post("/api/v1/pulse/analyze", json={
        "equipment_id": "B",
        "readings": [{"timestamp": "2026-08-20T08:00:00", "equipment_id": "B",
                      "temperature_c": 55.0, "vibration_mm_s": 6.4, "pressure_bar": 5.0}],
    })
    body = response.json()
    assert body["anomaly"]["severity"] == "critical"
    assert body["confidence"]["score"] >= 70
    assert body["confidence"]["abstain"] is False


def test_a_flat_series_with_nothing_wrong_abstains():
    flat = [{"timestamp": f"2026-08-20T{i:02d}:00:00", "equipment_id": "B",
             "temperature_c": 55.0, "vibration_mm_s": 2.0, "pressure_bar": 5.0}
            for i in range(20)]
    body = client.post("/api/v1/pulse/analyze",
                       json={"equipment_id": "B", "readings": flat}).json()
    assert body["anomaly"]["severity"] == "normal"
    assert body["confidence"]["abstain"] is True


def test_rate_limiter_rejects_a_flood():
    import backend.app.main as api

    original, api.RATE_LIMIT = api.RATE_LIMIT, 3
    api._hits.clear()
    try:
        payload = {"equipment_id": "B", "readings": [
            {"timestamp": "2026-08-20T08:00:00", "equipment_id": "B",
             "temperature_c": 55.0, "vibration_mm_s": 2.0, "pressure_bar": 5.0}]}
        codes = [client.post("/api/v1/pulse/analyze", json=payload).status_code
                 for _ in range(5)]
        assert 429 in codes
    finally:
        api.RATE_LIMIT = original
        api._hits.clear()


def test_health_is_reachable_under_the_api_prefix():
    """Production rewrites everything outside /api to the SPA, so a probe on
    bare /health would get HTML back."""
    assert client.get("/api/v1/health").json()["status"] == "ok"


# --- calibration: the healthy false-positive rate ---------------------------
#
# The severity boundary used to be a fixed `agg_score < 0.50`, which sat exactly
# on the Isolation Forest's noise floor. Measured on this population it reported
# 41% of healthy machines as drifting, and 27% as having a >50% chance of
# failing within seven days. These tests are the guard against that returning.

def test_healthy_machines_are_not_reported_as_drifting():
    """A shop-floor tool that cries drift on a clean machine is worse than
    useless, so the healthy false-positive rate is a hard budget."""
    from eval.healthy_population import population

    severities = [score_readings(series)["severity"] for series in population(200)]
    drifting = sum(s != "normal" for s in severities)
    rate = drifting / len(severities)
    assert rate <= 0.05, (
        f"{drifting}/{len(severities)} healthy machines were reported as drifting "
        f"({rate:.1%}). Re-run eval/calibrate.py."
    )


def test_the_drift_cut_still_matches_the_population_it_was_set_from():
    """The cut in model/anomaly.py is measured, not chosen. If anything that
    moves the score changes, this fails rather than the tool quietly drifting
    back to flagging healthy machines."""
    from eval.healthy_population import population
    from model.anomaly import DRIFT_MONITOR, BloomPulseAnomaly

    drifts = []
    for readings in population(200):
        engine = BloomPulseAnomaly()
        engine.score(readings)
        if engine.last_drift is not None:
            drifts.append(engine.last_drift)
    assert drifts, "no series in the healthy population could be modelled"
    crossed = sum(d > DRIFT_MONITOR for d in drifts) / len(drifts)
    assert crossed <= 0.05, (
        f"{crossed:.1%} of the healthy population crossed DRIFT_MONITOR "
        f"({DRIFT_MONITOR}). Re-run eval/calibrate.py and update the constants."
    )


def test_the_model_escalates_drift_that_no_published_limit_catches():
    """The model has to earn its place. A machine drifting clear of its own
    baseline escalates before anything published is crossed, which is the one
    thing the threshold gates cannot do."""
    import numpy as np

    from model.anomaly import (
        TEMP_RISE_THRESHOLD, TREND_MONITOR, VIB_NORMAL, BloomPulseAnomaly,
    )

    rng = np.random.default_rng(0)
    readings = [{
        "timestamp": f"2026-08-20T{i // 60:02d}:{i % 60:02d}:00",
        "equipment_id": "BRG-05-A",
        "temperature_c": float(52 + 0.22 * i + rng.normal(0, 0.5)),
        "vibration_mm_s": float(1.8 + 0.012 * i + rng.normal(0, 0.07)),
        "pressure_bar": float(5.0 + rng.normal(0, 0.03)),
    } for i in range(60)]

    engine = BloomPulseAnomaly()
    result = engine.score(readings)

    # Nothing published is breached...
    assert result["gate_breached"] == [], result["gate_breached"]
    assert result["metrics"]["max_vib"] < VIB_NORMAL
    assert result["metrics"]["max_temp_rise"] < TEMP_RISE_THRESHOLD
    # ...and a model instrument is the reason the verdict is not "normal".
    assert engine.last_trend_z is not None
    assert engine.last_trend_z > TREND_MONITOR
    assert result["severity"] == "monitor"
    # The channel named is the one that moved, and it is not vibration here.
    assert result["contributing_feature"] == "temperature_rise"


def test_temperature_rise_is_measured_from_the_start_of_the_series():
    """A rise has to be measured from the beginning. The baseline used to be the
    mean of the first eight readings, which on a shorter series was the mean of
    the whole series and reported roughly half the real rise."""
    readings = [{
        "timestamp": f"2026-08-20T{i:02d}:00:00", "equipment_id": "B",
        "temperature_c": 50.0 + 1.2 * i, "vibration_mm_s": 2.0, "pressure_bar": 5.0,
    } for i in range(8)]
    result = score_readings(readings)
    actual = readings[-1]["temperature_c"] - readings[0]["temperature_c"]
    reported = result["metrics"]["max_temp_rise"]
    assert reported > actual * 0.8, (
        f"reported {reported} C for an actual rise of {actual} C"
    )


def test_the_trend_cut_still_matches_the_population_it_was_set_from():
    """The trend cut is measured from the same healthy population as the forest
    cut, and a test fails if either stops matching it."""
    from eval.healthy_population import population
    from model.anomaly import TREND_MONITOR, BloomPulseAnomaly

    zs = []
    for readings in population(200):
        engine = BloomPulseAnomaly()
        engine.score(readings)
        if engine.last_trend_z is not None:
            zs.append(engine.last_trend_z)
    assert zs, "no series in the healthy population could be modelled"
    crossed = sum(z > TREND_MONITOR for z in zs) / len(zs)
    assert crossed <= 0.05, (
        f"{crossed:.1%} of the healthy population crossed TREND_MONITOR "
        f"({TREND_MONITOR}). Re-run eval/calibrate.py and update the constants."
    )


def test_a_smooth_thermal_ramp_is_caught():
    """The case an Isolation Forest structurally cannot see: every point on a
    slow ramp looks ordinary next to the one before it, so a machine heating
    steadily for days used to score as normal. The trend test catches it, and it
    is the reason that instrument exists."""
    from model.anomaly import TEMP_RISE_THRESHOLD

    readings = [{
        "timestamp": f"2026-08-20T{i // 60:02d}:{i % 60:02d}:00",
        "equipment_id": "BRG-05-A",
        "temperature_c": 50.0 + 0.30 * i,
        "vibration_mm_s": 2.0,
        "pressure_bar": 5.0,
    } for i in range(40)]

    result = score_readings(readings)

    # A steady 11.4 C climb, under the 15 C published trigger, so the gates stay
    # silent and the model has to carry it.
    assert result["gate_breached"] == [], result["gate_breached"]
    assert result["metrics"]["max_temp_rise"] < TEMP_RISE_THRESHOLD
    assert result["severity"] != "normal", result
    assert result["contributing_feature"] == "temperature_rise", result


def test_a_flat_machine_with_ordinary_noise_stays_normal():
    """The trend test must not fire on noise. This is the same budget as the
    forest cut, asserted through the whole pipeline."""
    import numpy as np

    from eval.healthy_population import healthy_series

    severities = [score_readings(healthy_series(seed))["severity"] for seed in range(100)]
    drifting = sum(s != "normal" for s in severities)
    assert drifting / len(severities) <= 0.05, (
        f"{drifting}/100 healthy machines were reported as drifting"
    )


def test_the_response_publishes_no_probability_claim():
    """Nothing in this project is calibrated against failure events, so the API
    must not put a probability in front of a maintenance supervisor."""
    body = upload(open("model/sample_anomaly.csv", "rb").read()).json()
    anomaly = body["anomaly"]
    assert "failure_probability_7d" not in anomaly
    assert "predicted_failure_days" not in anomaly
    assert "anomaly_index" in anomaly
    assert anomaly["inspection_window_days"] == 3


# --- rate limiter identity and growth ---------------------------------------

def test_rate_limiter_buckets_per_forwarded_client():
    """Behind a proxy `request.client.host` is the proxy, so keying on it put
    every visitor in one bucket and rate-limited the whole public demo at once."""
    import backend.app.main as api

    original, api.RATE_LIMIT = api.RATE_LIMIT, 3
    api._hits.clear()
    api._last_sweep = 0.0
    try:
        payload = {"equipment_id": "B", "readings": [
            {"timestamp": "2026-08-20T08:00:00", "equipment_id": "B",
             "temperature_c": 55.0, "vibration_mm_s": 2.0, "pressure_bar": 5.0}]}
        codes = [client.post("/api/v1/pulse/analyze", json=payload,
                             headers={"x-forwarded-for": f"203.0.113.{i}"}).status_code
                 for i in range(8)]
        assert set(codes) == {200}, codes
        assert len(api._hits) == 8, api._hits
    finally:
        api.RATE_LIMIT = original
        api._hits.clear()


def test_rate_limiter_evicts_idle_buckets():
    """The bucket dict is keyed on caller-supplied addresses, so it must not be
    able to grow without bound."""
    import time
    from collections import deque

    import backend.app.main as api

    api._hits.clear()
    api._last_sweep = 0.0
    try:
        for i in range(50):
            api._hits[f"198.51.100.{i}"] = deque([1.0])  # long idle
        now = time.monotonic()
        api._hits["active"] = deque([now])
        api._sweep(now)
        assert list(api._hits) == ["active"], list(api._hits)
    finally:
        api._hits.clear()
        api._last_sweep = 0.0


# --- provenance --------------------------------------------------------------

def test_only_passages_that_declare_published_provenance_read_as_published():
    """The flag defaults to synthetic and is cleared only by an explicit marker,
    so a passage written for the demo cannot be shown as a standard. The old
    rule searched the section for the literal word "synthetic", which an
    invented passage could simply avoid using."""
    from backend.app.rag.citations import passages

    collected = passages()
    assert collected["Sec 1910.147 - Control of Hazardous Energy (Lockout/Tagout)"].synthetic is False
    assert collected["Sec 1910.212 - General Requirements for All Machines"].synthetic is False
    assert collected["Bearing Unit Model: NTN UCFCX05"].synthetic is True
    assert collected["ISO 10816-3 - Vibration Severity (Industrial)"].synthetic is True
    assert collected["Siemens Simotics Motor - Predictive Thresholds"].synthetic is True
    # Falsely attributed to ISO 55000, which does not contain it.
    assert "Maintenance Work Order Template" not in collected

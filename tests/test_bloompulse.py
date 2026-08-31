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
    first = score_readings(healthy)["anomaly_score"]
    score_readings(failing)
    assert score_readings(healthy)["anomaly_score"] == first


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

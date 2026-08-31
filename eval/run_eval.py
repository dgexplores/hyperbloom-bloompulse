"""Measure what the pitch claims, rather than asserting it.

    PYTHONPATH=. python eval/run_eval.py

Metrics:
  span_fidelity     fraction of returned spans found verbatim in a corpus file.
                    This is the meaningful faithfulness number for extractive
                    retrieval: a span that is not in the corpus was invented.
  citation_coverage fraction of verdicts carrying at least one citation.
  severity_accuracy agreement with hand-labelled synthetic fixtures.
  abstention_rate   fraction of verdicts below the confidence floor.
  latency_ms        p50 and p95 over the fixture set.
"""
from __future__ import annotations

import json
import math
import statistics
import time
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.rag.citations import SOURCES_DIR, corpus_version

ROOT = Path(__file__).resolve().parent.parent
client = TestClient(app)


def series(n, vib, temp, pressure=5.0, drift=0.0, flat=False):
    """Fixtures carry a little deterministic noise, because a real sensor never
    reads the same value twice and a flat line means a stuck channel."""
    def wobble(i, k):
        return 0.0 if flat else math.sin(i * k) * 0.5 + math.cos(i * k * 1.7) * 0.3
    return [{
        "timestamp": f"2026-08-20T{i // 60:02d}:{i % 60:02d}:00",
        "equipment_id": "BRG-05-A",
        "temperature_c": round(temp + wobble(i, 1.1) * 2.2 + drift * i * 1.6, 2),
        "vibration_mm_s": round(vib + wobble(i, 0.7) * 0.22 + drift * i * 0.28, 3),
        "pressure_bar": round(pressure + wobble(i, 1.4) * 0.1, 3),
    } for i in range(n)]


# Hand-labelled fixtures. The label is what a technician reading ISO 10816-3
# would call the series, decided from the thresholds, not from the model.
FIXTURES = [
    ("healthy steady",        series(30, 1.8, 52.0),                 "normal"),
    ("healthy with noise",    series(30, 2.4, 58.0, pressure=5.1),   "normal"),
    ("stuck flat sensor",     series(30, 2.0, 55.0, flat=True),      "normal"),
    ("zone C creep",          series(30, 3.4, 60.0),                 "monitor"),
    ("zone D vibration",      series(30, 5.2, 60.0),                 "critical"),
    ("progressive bearing",   series(30, 1.9, 54.0, drift=1.0),      "critical"),
    ("thermal runaway",       series(30, 2.0, 52.0, drift=0.55),     "critical"),
]


def corpus_text() -> str:
    return " ".join(
        " ".join(path.read_text(encoding="utf-8").split())
        for path in sorted(SOURCES_DIR.glob("*.md"))
    )


def main() -> None:
    haystack = corpus_text()
    spans_total = spans_found = 0
    cited = correct = abstained = 0
    latencies: list[float] = []
    rows = []

    for name, readings, expected in FIXTURES:
        started = time.perf_counter()
        response = client.post("/api/v1/pulse/analyze",
                               json={"equipment_id": "BRG-05-A", "readings": readings})
        latencies.append((time.perf_counter() - started) * 1000)
        response.raise_for_status()
        body = response.json()

        severity = body["anomaly"]["severity"]
        citations = body["citations"]
        cited += bool(citations)
        correct += severity == expected
        abstained += bool(body["confidence"]["abstain"])

        for citation in citations:
            spans_total += 1
            spans_found += " ".join(citation["span_text"].split()) in haystack

        rows.append({
            "fixture": name, "expected": expected, "actual": severity,
            "match": severity == expected, "citations": len(citations),
            "confidence": body["confidence"]["score"],
        })

    n = len(FIXTURES)
    report = {
        "corpus_version": corpus_version(),
        "fixtures": n,
        "span_fidelity": round(spans_found / spans_total, 4) if spans_total else None,
        "spans_checked": spans_total,
        "citation_coverage": round(cited / n, 4),
        "severity_accuracy": round(correct / n, 4),
        "abstention_rate": round(abstained / n, 4),
        "latency_ms_p50": round(statistics.median(latencies), 1),
        "latency_ms_p95": round(sorted(latencies)[int(n * 0.95) - 1], 1),
        "detail": rows,
    }

    out = ROOT / "eval" / "report.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"corpus            {report['corpus_version']}")
    print(f"span fidelity     {report['span_fidelity']}  ({spans_found}/{spans_total} verbatim in corpus)")
    print(f"citation coverage {report['citation_coverage']}")
    print(f"severity accuracy {report['severity_accuracy']}  ({correct}/{n})")
    print(f"abstention rate   {report['abstention_rate']}")
    print(f"latency p50/p95   {report['latency_ms_p50']} / {report['latency_ms_p95']} ms")
    for row in rows:
        mark = "ok  " if row["match"] else "MISS"
        print(f"  {mark} {row['fixture']:22} expected {row['expected']:8} got {row['actual']:8} "
              f"cites {row['citations']} conf {row['confidence']}")


if __name__ == "__main__":
    main()

"""Tests for the displacement confidence interval (model/confidence.py).

The trend test reports a point displacement; this reports how much that
number wobbles under resampling. A monitor verdict whose displacement
confidence interval includes zero is a guess wearing a number, and the
pipeline abstains instead of publishing it.
"""
import time

import numpy as np

from model.confidence import trend_ci


def _channel_pair(shift, spread=1.0, n_open=8, n_recent=5, seed=0):
    rng = np.random.default_rng(seed)
    opening = rng.normal(0, spread, n_open)
    recent = rng.normal(shift, spread, n_recent)
    return opening, recent


def test_ci_covers_true_shift():
    # Large enough windows that sample stats concentrate near truth.
    opening, recent = _channel_pair(shift=8.0, n_open=200, n_recent=60, seed=0)
    lo, hi = trend_ci(opening, recent, B=1000, seed=1)
    assert lo <= 8.0 <= hi


def test_ci_includes_zero_on_pure_noise():
    opening, recent = _channel_pair(shift=0.0, n_open=60, n_recent=30)
    lo, hi = trend_ci(opening, recent, B=1000, seed=1)
    assert lo <= 0.0 <= hi


def test_ci_tightens_with_stronger_signal():
    narrow = trend_ci(*_channel_pair(shift=10.0), B=1000, seed=1)
    wide = trend_ci(*_channel_pair(shift=10.0, spread=3.0), B=1000, seed=1)
    assert (narrow[1] - narrow[0]) < (wide[1] - wide[0])


def test_ci_vectorized_fast():
    opening, recent = _channel_pair(shift=5.0, n_open=60, n_recent=30)
    start = time.perf_counter()
    trend_ci(opening, recent, B=1000, seed=1)
    assert (time.perf_counter() - start) < 0.05


def test_ci_reproducible_with_seed():
    args = _channel_pair(shift=5.0)
    assert trend_ci(*args, B=500, seed=7) == trend_ci(*args, B=500, seed=7)


def test_ci_endpoints_ordered():
    lo, hi = trend_ci(*_channel_pair(shift=-6.0), B=500, seed=2)
    assert lo <= hi
    assert hi < 0.0


def _fragile_csv(seed=10, n=30):
    import numpy as np

    rng = np.random.default_rng(seed)
    temp = 56 + 0.03 * np.arange(n) + rng.normal(0, 0.8, n)
    vib = 2.0 + rng.normal(0, 0.15, n)
    lines = ["timestamp,equipment_id,temperature_c,vibration_mm_s,pressure_bar,rpm"]
    for i in range(n):
        lines.append(
            f"2026-08-20T{i // 60:02d}:{i % 60:02d}:00,X,{temp[i]:.2f},"
            f"{max(0.1, vib[i]):.2f},5.0,1750"
        )
    return "\n".join(lines).encode()


def test_fragile_monitor_abstains_end_to_end():
    from fastapi.testclient import TestClient

    from backend.app.main import app

    resp = TestClient(app).post(
        "/api/v1/pulse/upload?equipment_id=X",
        files={"file": ("fragile.csv", _fragile_csv(), "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["anomaly"]["severity"] == "monitor"
    assert body["trend_ci"][0] <= 0 <= body["trend_ci"][1]
    assert body["confidence"]["abstain"] is True
    assert "resampling" in body["confidence"]["rationale"]


def test_genuine_creep_does_not_abstain():
    import numpy as np
    from fastapi.testclient import TestClient

    from backend.app.main import app

    rng = np.random.default_rng(4)
    n = 30
    temp = 55 + 0.15 * np.arange(n) + rng.normal(0, 0.5, n)
    vib = 2.0 + rng.normal(0, 0.1, n)
    lines = ["timestamp,equipment_id,temperature_c,vibration_mm_s,pressure_bar,rpm"]
    for i in range(n):
        lines.append(
            f"2026-08-20T{i // 60:02d}:{i % 60:02d}:00,X,{temp[i]:.2f},"
            f"{max(0.1, vib[i]):.2f},5.0,1750"
        )
    resp = TestClient(app).post(
        "/api/v1/pulse/upload?equipment_id=X",
        files={"file": ("creep.csv", "\n".join(lines).encode(), "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["anomaly"]["severity"] == "monitor"
    assert body["trend_ci"][0] > 0
    # The floor still abstains every monitor (62 < 70); the CI rule only
    # decides whether the abstention names fragility as its reason.
    assert body["confidence"]["abstain"] is True
    assert "resampling" not in body["confidence"]["rationale"]

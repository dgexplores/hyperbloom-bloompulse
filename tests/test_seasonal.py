"""Tests for seasonal handling (model/seasonal.py + integration).

A periodic signal sampled over part of its cycle aliases into a false
displacement: the opening window sits in a trough, the recent window on a
crest, and a pure mean comparison cries drift on a healthy machine.

Honest boundary, documented in model/seasonal.py: a cycle is only
identifiable when the series spans enough of it (period <= n/2). Shorter
periods are detected and reported; longer ones cannot be separated from
drift within one series, so the verdict stands and the boundary is locked
by the tests below instead of guessed around.
"""
import pytest

from model.anomaly import BloomPulseAnomaly
from model.seasonal import seasonal_period


def _series(period=None, amp_temp=0.0, amp_vib=0.0, slope_temp=0.0, n=40, seed=11):
    import numpy as np

    rng = np.random.default_rng(seed)
    t = np.arange(n)
    cyc = np.sin(2 * np.pi * t / period) if period else 0.0
    temp = 55 + slope_temp * t + amp_temp * cyc + rng.normal(0, 0.4, n)
    vib = 1.9 + amp_vib * cyc + rng.normal(0, 0.07, n)
    return [
        {
            "timestamp": f"2026-08-20T{i // 60:02d}:{i % 60:02d}:00",
            "equipment_id": "X",
            "temperature_c": float(temp[i]),
            "vibration_mm_s": float(max(0.1, vib[i])),
            "pressure_bar": 5.0,
        }
        for i in range(n)
    ]


def test_identifiable_cycle_detected_and_scores_normal():
    """Period 16 in 40 readings: detected, no false verdict."""
    readings = _series(period=16, amp_temp=2.0, amp_vib=0.3)
    engine = BloomPulseAnomaly()
    result = engine.score(readings)
    assert result["seasonal_period"] == 16
    assert result["severity"] == "normal", result["severity"]


def test_half_cycle_aliasing_never_escalates_past_monitor():
    """Period 48 in 40 readings is unidentifiable: verdict stands, capped."""
    readings = _series(period=48, amp_temp=3.0)
    engine = BloomPulseAnomaly()
    result = engine.score(readings)
    assert result["seasonal_period"] is None
    assert result["severity"] in ("normal", "monitor"), result["severity"]


def test_true_ramp_still_escalates():
    """Seasonal handling must not blind the trend test to a real ramp."""
    readings = _series(slope_temp=0.22, n=60, seed=0)
    result = BloomPulseAnomaly().score(readings)
    assert result["seasonal_period"] is None
    assert result["severity"] in ("monitor", "alert"), result["severity"]


def test_period_detected_on_cyclic_opening():
    import numpy as np

    t = np.arange(8)
    x = np.sin(2 * np.pi * t / 4)
    assert seasonal_period(x) == 4


def test_no_period_on_noise():
    import numpy as np

    rng = np.random.default_rng(3)
    assert seasonal_period(rng.normal(0, 1, 40)) is None


def test_no_period_on_ramp():
    import numpy as np

    x = np.arange(40, dtype=float)
    assert seasonal_period(x) is None


def test_short_series_has_no_period():
    assert seasonal_period([1.0, 2.0, 3.0]) is None

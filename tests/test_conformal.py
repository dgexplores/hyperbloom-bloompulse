"""Tests for split-conformal drift sets (model/conformal.py).

One-sided sets over {no-drift}: a series scores its worst normalized
instrument margin, calibrated on healthy machines. The set answers one
question only — "can no-drift be ruled out?" Drift itself is never ruled
out by this test; that is documented, not hidden.
"""
import math

from model.conformal import (
    CONFORMAL_DRIFT_Q95,
    calibration_threshold,
    drift_nonconformity,
    prediction_set,
)


def test_threshold_uses_plus_one_correction():
    scores = list(range(100))
    assert calibration_threshold(scores, alpha=0.05) == scores[math.ceil(101 * 0.95) - 1]


def test_threshold_monotone_in_alpha():
    scores = [float(i) / 10 for i in range(200)]
    assert calibration_threshold(scores, alpha=0.01) >= calibration_threshold(scores, alpha=0.05)


def test_clean_series_scores_low():
    import numpy as np

    rng = np.random.default_rng(0)
    readings = [
        {
            "timestamp": f"2026-08-20T{i // 60:02d}:{i % 60:02d}:00",
            "equipment_id": "X",
            "temperature_c": float(55 + rng.normal(0, 0.5)),
            "vibration_mm_s": float(1.9 + rng.normal(0, 0.07)),
            "pressure_bar": 5.0,
        }
        for i in range(30)
    ]
    assert drift_nonconformity(readings) < CONFORMAL_DRIFT_Q95


def test_ramp_scores_high():
    import numpy as np

    rng = np.random.default_rng(0)
    readings = [
        {
            "timestamp": f"2026-08-20T{i // 60:02d}:{i % 60:02d}:00",
            "equipment_id": "X",
            "temperature_c": float(52 + 0.22 * i + rng.normal(0, 0.5)),
            "vibration_mm_s": float(1.8 + 0.012 * i + rng.normal(0, 0.07)),
            "pressure_bar": 5.0,
        }
        for i in range(60)
    ]
    assert drift_nonconformity(readings) > CONFORMAL_DRIFT_Q95


def test_set_rules_out_no_drift_on_ramp():
    assert prediction_set(10.0, CONFORMAL_DRIFT_Q95) == [0, 1]


def test_set_keeps_no_drift_on_clean():
    assert prediction_set(0.0, CONFORMAL_DRIFT_Q95) == [0]


def test_validity_on_held_out_healthy():
    from eval.healthy_population import healthy_series

    cal = [drift_nonconformity(healthy_series(s)) for s in range(200)]
    threshold = calibration_threshold(cal, alpha=0.05)
    held_out = [drift_nonconformity(healthy_series(s)) for s in range(200, 600)]
    violation = sum(v > threshold for v in held_out) / len(held_out)
    assert violation <= 0.06, violation


def test_power_on_drift_fixtures():
    import sys

    sys.path.insert(0, "eval")
    from run_eval import DRIFT_FIXTURES

    for name, readings in DRIFT_FIXTURES:
        assert drift_nonconformity(readings) > CONFORMAL_DRIFT_Q95, name

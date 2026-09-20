"""Split-conformal drift sets, calibrated on healthy machines.

Nonconformity of a series is its worst normalized instrument margin:
forest drift over DRIFT_ALERT, trend z over TREND_MONITOR. Both
normalizers are the instruments' own cuts, so the score moves with them
instead of alongside them.

The threshold below is measured by eval/calibrate.py on 200 healthy
series (95% quantile, +1 finite-sample correction) and pasted here. At
runtime the set answers one question only: can no-drift be ruled out?
[0] means yes, it still stands; [0, 1] means no, review the machine.
Drift is never ruled out by this test.
"""
from __future__ import annotations

import math

CONFORMAL_DRIFT_Q95 = 0.313


def calibration_threshold(scores: list[float], alpha: float = 0.05) -> float:
    """95% quantile with the standard +1 finite-sample correction."""
    ordered = sorted(scores)
    index = math.ceil((len(ordered) + 1) * (1.0 - alpha)) - 1
    return ordered[max(0, min(index, len(ordered) - 1))]


def _margins(drift: float | None, trend: float | None) -> float:
    from model.anomaly import DRIFT_ALERT, TREND_MONITOR

    d = drift if drift is not None else -1.0
    t = trend if trend is not None else 0.0
    return max(d / DRIFT_ALERT, t / TREND_MONITOR)


def drift_nonconformity(readings: list[dict]) -> float:
    """Worst normalized instrument margin for one series."""
    from model.anomaly import BloomPulseAnomaly

    engine = BloomPulseAnomaly()
    engine.score(readings)
    return _margins(engine.last_drift, engine.last_trend_z)


def prediction_set(score: float, threshold: float = CONFORMAL_DRIFT_Q95) -> list[int]:
    """One-sided set: [0] rules no-drift in, [0, 1] sends it for review."""
    if score <= threshold:
        return [0]
    return [0, 1]

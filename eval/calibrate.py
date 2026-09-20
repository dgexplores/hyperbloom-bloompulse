"""Set the drift cuts in model/anomaly.py from a measured healthy population.

    PYTHONPATH=. python eval/calibrate.py

Two instruments feed the severity floor, and both need cuts:

  forest drift  The recent window's score minus this series' own noise floor.
                Replaced a fixed `agg_score < 0.50`, which sat exactly on the
                model's noise floor and reported 41% of healthy machines as
                drifting.
  trend z       Signal-to-noise of the recent window against the opening window,
                per channel. Catches a smooth ramp, which an Isolation Forest
                structurally cannot see.

This script measures both against a healthy population and prints the cuts they
imply. Run it after anything that moves the score, then paste the values into
model/anomaly.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.healthy_population import population  # noqa: E402
from model.anomaly import BloomPulseAnomaly  # noqa: E402

# The false-positive budget. A tool that cries drift on a healthy machine is
# worse than useless on a shop floor, so this is deliberately tight.
FALSE_POSITIVE_BUDGET = 0.02

# Tolerance when comparing the printed cuts against the ones in the source.
TOLERANCE = 0.011


def measure(readings: list[dict]) -> tuple[float | None, float | None, float | None]:
    """All three drift instruments for one series, without the gates involved."""
    engine = BloomPulseAnomaly()
    engine.score(readings)
    return engine.last_drift, engine.last_trend_z, engine.last_physics


def quantiles(values: np.ndarray, unit: str) -> None:
    for q in (50, 90, 95, 99):
        print(f"  p{q:<3} {np.percentile(values, q):>8.3f}{unit}")
    print(f"  max  {values.max():>8.3f}{unit}")


def main() -> None:
    size = 400
    pairs = [measure(series) for series in population(size)]

    drift = np.array([d for d, _, _ in pairs if d is not None])
    trend = np.array([t for _, t, _ in pairs if t is not None])
    physics = np.array([p for _, _, p in pairs if p is not None])

    print(f"healthy population: {size} series "
          f"({size - len(drift)} too short or too flat to model)")

    print(f"\nforest drift (n={len(drift)})")
    quantiles(drift, "")

    print(f"\ntrend z (n={len(trend)})")
    quantiles(trend, "")

    print(f"\nphysics consistency (n={len(physics)})")
    quantiles(physics, "")

    # DRIFT_MONITOR: at most FALSE_POSITIVE_BUDGET of healthy machines cross it.
    # It comes out below zero, which is the point: a healthy machine's recent
    # window scores lower than its own baseline did, so any positive drift is
    # already meaningful.
    drift_monitor = round(float(np.quantile(drift, 1.0 - FALSE_POSITIVE_BUDGET)), 2)
    drift_alert = round(max(drift.max() * 5, 0.05), 2)

    # TREND_MONITOR: the largest value a healthy machine produced, plus a
    # margin. Measured drift fixtures sit far above it, so the cut lands in an
    # empty band rather than on a cliff edge.
    trend_monitor = round(float(trend.max() * 1.2), 1)
    trend_alert = round(float(trend.max() * 4), 1)

    print(f"\nDRIFT_MONITOR = {drift_monitor}   "
          f"-> flags {(drift > drift_monitor).mean():.2%} of healthy machines "
          f"(budget {FALSE_POSITIVE_BUDGET:.0%})")
    print(f"DRIFT_ALERT   = {drift_alert}   "
          f"-> {drift_alert / max(drift.max(), 1e-9):.1f}x the largest healthy drift")
    print(f"TREND_MONITOR = {trend_monitor}   "
          f"-> flags {(trend > trend_monitor).mean():.2%} of healthy machines")
    print(f"TREND_ALERT   = {trend_alert}   "
          f"-> {trend_alert / max(trend.max(), 1e-9):.1f}x the largest healthy trend")

    # PHYSICS_CONSISTENCY_ALERT: healthy machines sit at ~0.5 (stillness).
    # The cut sits in the empty band above the largest healthy value.
    physics_alert = 0.9
    print(f"PHYSICS_CONSISTENCY_ALERT = {physics_alert}   "
          f"-> healthy max {physics.max():.3f}, "
          f"flags {(physics > physics_alert).mean():.2%} of healthy machines")

    # CONFORMAL_DRIFT_Q95: split-conformal threshold on the worst normalized
    # instrument margin, calibrated on the first 200 healthy series.
    from model.conformal import CONFORMAL_DRIFT_Q95, calibration_threshold, drift_nonconformity

    cal_scores = [drift_nonconformity(series) for series in population(200)]
    conformal_measured = round(calibration_threshold(cal_scores), 3)
    print(f"\nconformal nonconformity (n={len(cal_scores)})")
    quantiles(np.array(cal_scores), "")
    print(f"CONFORMAL_DRIFT_Q95 = {conformal_measured}   "
          f"-> pasted constant {CONFORMAL_DRIFT_Q95}")

    from model.anomaly import (
        DRIFT_ALERT, DRIFT_MONITOR, TREND_ALERT, TREND_MONITOR,
    )
    from model.physics import PHYSICS_CONSISTENCY_ALERT

    print()
    print("in model/anomaly.py: "
          f"DRIFT_MONITOR={DRIFT_MONITOR} DRIFT_ALERT={DRIFT_ALERT} "
          f"TREND_MONITOR={TREND_MONITOR} TREND_ALERT={TREND_ALERT}")
    mismatches = [
        (name, current, measured)
        for name, current, measured in (
            ("DRIFT_MONITOR", DRIFT_MONITOR, drift_monitor),
            ("DRIFT_ALERT", DRIFT_ALERT, drift_alert),
            ("TREND_MONITOR", TREND_MONITOR, trend_monitor),
            ("TREND_ALERT", TREND_ALERT, trend_alert),
            ("PHYSICS_CONSISTENCY_ALERT", PHYSICS_CONSISTENCY_ALERT, physics_alert),
            ("CONFORMAL_DRIFT_Q95", CONFORMAL_DRIFT_Q95, conformal_measured),
        )
        if abs(current - measured) > TOLERANCE
    ]
    if mismatches:
        for name, current, measured in mismatches:
            print(f"  ^ {name} is {current}, measured {measured}. Update it.")
        sys.exit(1)
    print("  ^ all six match the measured cuts.")


if __name__ == "__main__":
    main()

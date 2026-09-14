"""Set the drift cuts in model/anomaly.py from a measured healthy population.

    PYTHONPATH=. python eval/calibrate.py

The severity boundary used to be a fixed `agg_score < 0.50`. An Isolation Forest
score has no absolute meaning - it depends entirely on the series - so that cut
landed exactly on the model's noise floor and reported 41% of healthy machines
as drifting.

Drift is now measured per series, as the recent window standing clear of that
same series' own noise floor. The two cuts below are the only free parameters
left, and this script is where they come from. Run it after changing anything
that moves the score, then paste the printed values into model/anomaly.py.
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


def drift_of(readings: list[dict]) -> float | None:
    """The drift measure alone, without the gates getting involved."""
    engine = BloomPulseAnomaly()
    engine.score(readings)
    return engine.last_drift


def main() -> None:
    size = 400
    values = [drift_of(series) for series in population(size)]
    measured = np.array([v for v in values if v is not None])
    skipped = len(values) - len(measured)

    print(f"healthy population      {size} series ({skipped} too short or too flat to model)")
    print(f"  min                   {measured.min():+.4f}")
    print(f"  p50                   {np.percentile(measured, 50):+.4f}")
    print(f"  p90                   {np.percentile(measured, 90):+.4f}")
    print(f"  p95                   {np.percentile(measured, 95):+.4f}")
    print(f"  max                   {measured.max():+.4f}")

    # The monitor cut is placed so that at most FALSE_POSITIVE_BUDGET of the
    # healthy population crosses it. It comes out below zero, which is the
    # point: a healthy machine's recent window scores lower than its own
    # baseline did, so any positive drift is already meaningful.
    monitor = round(float(np.quantile(measured, 1.0 - FALSE_POSITIVE_BUDGET)), 2)
    observed = float((measured > monitor).mean())

    # The alert band needs to be unreachable without real movement, and there is
    # no labelled drift population to calibrate it against, so it is set as a
    # margin above the largest drift a healthy machine produced rather than
    # pretending to a probability.
    alert = round(max(measured.max() * 5, 0.05), 2)

    print()
    print(f"DRIFT_MONITOR = {monitor}   "
          f"-> flags {observed:.2%} of healthy machines (budget {FALSE_POSITIVE_BUDGET:.0%})")
    print(f"DRIFT_ALERT   = {alert}   "
          f"-> {alert / max(measured.max(), 1e-9):.1f}x the largest healthy drift "
          f"({measured.max():+.4f})")

    from model.anomaly import DRIFT_ALERT, DRIFT_MONITOR

    print()
    print(f"currently in model/anomaly.py: DRIFT_MONITOR={DRIFT_MONITOR} "
          f"DRIFT_ALERT={DRIFT_ALERT}")
    if abs(DRIFT_MONITOR - monitor) > 0.011 or abs(DRIFT_ALERT - alert) > 0.011:
        print("  ^ these differ from the measured cuts. Re-run and update them.")
    else:
        print("  ^ these match the measured cuts.")


if __name__ == "__main__":
    main()

"""
BloomPulse anomaly engine - CPU-only, deterministic, no hardware.

Isolation Forest over rolling sensor features, with ISO 10816-3 / NTN
threshold gates layered on top so a hard physical breach always escalates
regardless of what the unsupervised model thinks.
"""
from __future__ import annotations

import numpy as np

from model.iforest import IsolationForest

# Thresholds from corpus: ISO 10816-3 Table A.2 + NTN manual Sec 4.2
VIB_NORMAL = 2.8            # mm/s - Zone B/C boundary
VIB_ALERT = 4.5             # mm/s - Zone D, shutdown
TEMP_RISE_THRESHOLD = 15.0  # degrees C over baseline
PRESSURE_VARIANCE_ALERT = 12.0  # percent

RECENT_WINDOW = 5   # readings summarised as the current condition
MIN_BASELINE = 8    # readings needed before fitting on a baseline slice only
REFERENCE_READINGS = 3  # opening readings that define the temperature baseline

# Drift is the recent window standing clear of THIS series' own noise floor,
# not a distance from a universal constant. See score() for the measurement and
# eval/calibrate.py for the population these two cuts are set from.
#
# DRIFT_MONITOR is the 98th percentile of the healthy population, so a healthy
# machine crosses it 2% of the time. DRIFT_ALERT is five times the largest drift
# any healthy machine produced, which makes the alert band unreachable without
# real movement. Re-run eval/calibrate.py after anything that moves the score.
DRIFT_MONITOR = -0.01
DRIFT_ALERT = 0.10

FEATURES = ("temperature_c", "vibration_mm_s", "pressure_bar",
            "vib_rolling_mean", "temp_rise", "pressure_variance_pct")

# Column indices into FEATURES, named so the attribution below cannot drift out
# of step with the matrix if a feature is ever added.
I_TEMP, I_VIB, I_PRESS, I_VIB_ROLL, I_RISE, I_PVAR = range(6)


class BloomPulseAnomaly:
    """Single-use scorer. Construct one per series, because fitting is cheap
    and a shared instance would leak one series' baseline into the next
    request."""

    def __init__(self):
        # No scaler: the forest splits inside each feature's own range, so it
        # is scale invariant already. See tests/test_iforest.py.
        self.model = IsolationForest(n_estimators=150, random_state=42)
        # The drift measure from the last score() call, exposed so
        # eval/calibrate.py can set the cuts from the measurement itself rather
        # than from the severity it produces.
        self.last_drift: float | None = None

    def _features(self, readings: list[dict]) -> np.ndarray:
        """6-dim feature matrix, one row per reading. See FEATURES."""
        temps = np.array([r["temperature_c"] for r in readings], dtype=float)
        vibs = np.array([r["vibration_mm_s"] for r in readings], dtype=float)
        pressures = np.array(
            [r.get("pressure_bar") if r.get("pressure_bar") is not None else 5.0
             for r in readings], dtype=float)

        # centred rolling mean, window 5, clipped at the series edges
        vib_roll = np.array([vibs[max(0, i - 2):i + 3].mean() for i in range(len(vibs))])

        # Temperature rise measured against the opening readings. The median of
        # the first few is used rather than the mean of the first eight: on a
        # series shorter than eight the old baseline was the mean of the whole
        # series, which averaged a monotonic rise away and under-reported it by
        # roughly half. A rise has to be measured from the start, not from its
        # own middle.
        reference = float(np.median(temps[:REFERENCE_READINGS]))
        temp_rise = temps - reference

        mean_pressure = float(pressures.mean())
        denom = abs(mean_pressure) if abs(mean_pressure) > 1e-6 else 1.0
        pressure_var = np.abs(pressures - mean_pressure) / denom * 100

        return np.column_stack([temps, vibs, pressures, vib_roll, temp_rise, pressure_var])

    def score(self, readings: list[dict]) -> dict:
        if not readings:
            raise ValueError("at least one reading is required")

        X = self._features(readings)
        n = len(X)

        # The forest only means something given a baseline it can learn a
        # shape from. Too few rows, or a flat baseline with no variance at
        # all, and the model cannot say anything, so the threshold gates
        # decide alone.
        fit_slice = X[:max(MIN_BASELINE, n // 2)]
        modeled = n >= MIN_BASELINE and bool(fit_slice.var(axis=0).max() > 1e-9)

        if modeled:
            # Fit on the opening slice, assuming a series starts healthy and
            # degrades from there.
            self.model.fit(fit_slice)
            # What the model says about the data it was trained on is this
            # series' own noise floor. An Isolation Forest score has no
            # absolute meaning - it depends entirely on the series - so drift
            # is measured against that floor rather than against a fixed
            # constant. Comparing an absolute score to 0.50 put the severity
            # boundary exactly on the noise floor, which reported 41% of
            # healthy machines as drifting.
            floor = float(np.percentile(self.model.score_samples(fit_slice), 95))
            recent_score = float(np.mean(self.model.score_samples(X)[-RECENT_WINDOW:]))
            drift = recent_score - floor
        else:
            drift = None
        self.last_drift = drift

        recent = X[-RECENT_WINDOW:]
        max_vib = float(recent[:, I_VIB].max())
        max_temp_rise = float(recent[:, I_RISE].max())
        pressure_var = float(recent[:, I_PVAR].max())

        # Physical threshold gates. A real breach floors the score, and a
        # published limit is a measurement rather than an inference, so the
        # gates can never be talked down by the model.
        gate_floor = 0.0
        breached: dict[str, float] = {}
        if max_vib > VIB_ALERT:
            gate_floor = 0.82
            breached["vibration"] = max_vib / VIB_ALERT
        elif max_vib > VIB_NORMAL:
            gate_floor = max(gate_floor, 0.58)
            breached["vibration"] = max_vib / VIB_NORMAL
        if max_temp_rise > TEMP_RISE_THRESHOLD:
            gate_floor = max(gate_floor, 0.78)
            breached["temperature_rise"] = max_temp_rise / TEMP_RISE_THRESHOLD
        if pressure_var > PRESSURE_VARIANCE_ALERT:
            gate_floor = max(gate_floor, 0.71)
            breached["pressure_variance"] = pressure_var / PRESSURE_VARIANCE_ALERT

        # The model's own contribution. It is combined with the gates rather
        # than discarded by them, so a machine drifting clear of its baseline
        # still escalates before anything published has been crossed - which
        # is the entire reason for running a model here.
        drift_floor = 0.0
        if drift is not None:
            if drift > DRIFT_ALERT:
                drift_floor = 0.78
            elif drift > DRIFT_MONITOR:
                drift_floor = 0.58

        agg_score = float(np.clip(max(gate_floor, drift_floor), 0.0, 1.0))

        if agg_score < 0.50:
            severity, days = "normal", None
        elif agg_score < 0.65:
            severity, days = "monitor", 14
        elif agg_score < 0.82:
            severity, days = "alert", 7
        else:
            severity, days = "critical", 3

        # Name the channel the verdict actually turns on. Which one that is
        # depends on why the verdict fired, so the two cases are answered
        # differently rather than by one ratio that is only right for one.
        if breached:
            # A published limit decides: name the channel furthest past its own.
            contrib = max(breached.items(), key=lambda kv: kv[1])[0]
        elif modeled:
            # Nothing published is crossed, so the driver is whichever channel
            # has moved furthest from its own baseline, in units of its own
            # normal variation. An attribution, not a limit ratio.
            centre = fit_slice.mean(axis=0)
            spread = fit_slice.std(axis=0)
            spread = np.where(spread > 1e-9, spread, 1.0)
            z = (recent.mean(axis=0) - centre) / spread
            contrib = max(
                {"vibration": z[I_VIB],
                 "temperature_rise": z[I_RISE],
                 "pressure_variance": z[I_PVAR]}.items(),
                key=lambda kv: abs(kv[1]),
            )[0]
        else:
            contrib = "vibration"

        return {
            # 0..1 index of how far from baseline the machine has moved. Not a
            # probability, and named so that nobody reads it as one.
            "anomaly_index": round(agg_score, 3),
            "drift": round(drift, 4) if drift is not None else None,
            "gate_breached": sorted(breached),
            # A policy lookup on severity, not a prediction. See README.
            "inspection_window_days": days,
            "severity": severity,
            "contributing_feature": contrib,
            "baseline_modeled": modeled,
            "reading_count": n,
            "metrics": {
                "max_vib": round(max_vib, 3),
                "max_temp_rise": round(max_temp_rise, 3),
                "pressure_var": round(pressure_var, 2),
            },
        }


def score_readings(readings: list[dict]) -> dict:
    """Score one series. Fresh engine per call, see BloomPulseAnomaly."""
    return BloomPulseAnomaly().score(readings)

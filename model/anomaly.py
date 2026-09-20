"""
BloomPulse anomaly engine - CPU-only, deterministic, no hardware.

Isolation Forest over rolling sensor features, with ISO 10816-3 / NTN
threshold gates layered on top so a hard physical breach always escalates
regardless of what the unsupervised model thinks.
"""
from __future__ import annotations

import numpy as np

from model.confidence import trend_ci
from model.conformal import CONFORMAL_DRIFT_Q95, _margins, prediction_set
from model.iforest import IsolationForest
from model.physics import (
    DEFAULT_BEARING,
    PHYSICS_CONSISTENCY_ALERT,
    defect_frequencies,
    friction_consistency,
)
from model.seasonal import seasonal_period

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
# eval/calibrate.py for the population these cuts are set from.
#
# DRIFT_MONITOR is the 98th percentile of the healthy population, so a healthy
# machine crosses it 2% of the time. DRIFT_ALERT is five times the largest drift
# any healthy machine produced, which makes the alert band unreachable without
# real movement. Re-run eval/calibrate.py after anything that moves the score.
DRIFT_MONITOR = -0.01
DRIFT_ALERT = 0.10

# A second, independent drift instrument: signal-to-noise of the recent window
# against the opening window, per channel.
#
# The forest cannot see a smooth ramp. An Isolation Forest isolates points that
# are unlike their neighbours, and every point on a slow ramp looks ordinary next
# to the one before it, so a machine heating steadily for two days scored as
# normal. This measures the thing a technician actually reads off a chart: has
# this channel moved further than it normally wanders?
#
# Measured over 400 healthy machines the largest value any of them produced was
# 5.13, and over the drift fixtures the smallest was 12.14, so the cut sits in a
# wide empty band rather than on a cliff edge. eval/calibrate.py prints both.
TREND_OPENING = 8       # readings that define "how it normally wanders"
TREND_MONITOR = 6.2
TREND_ALERT = 20.5

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
        self.last_trend_z: float | None = None
        self.last_physics: float | None = None

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

    def _trend(self, X: np.ndarray) -> dict[str, float]:
        """Per-channel signal-to-noise of the recent window against the opening.

        How far the recent window has moved, in units of how much this channel
        normally wanders. Scale free, per series, and it does not care whether
        the movement is a step or a slow ramp.
        """
        opening = X[:TREND_OPENING]
        recent = X[-RECENT_WINDOW:]
        spread = opening.std(axis=0)
        spread = np.where(spread > 1e-9, spread, np.nan)
        z = np.nan_to_num((recent.mean(axis=0) - opening.mean(axis=0)) / spread, nan=0.0)
        return {
            "vibration": float(z[I_VIB]),
            "temperature_rise": float(z[I_TEMP]),
            "pressure_variance": float(z[I_PRESS]),
        }

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

        # The second instrument. Both are combined below: the forest is good at
        # a channel that has gone erratic, the trend test is good at one that has
        # simply moved, and neither alone covers both.
        trend = self._trend(X)
        self.last_trend_z = max(abs(v) for v in trend.values()) if modeled else None

        # The third instrument: heat and vibration moving together is friction
        # evidence. It only ever confirms a displacement the trend test already
        # saw (never fires alone), escalating the ambiguous monitor band to
        # alert when the machine agrees with itself.
        if modeled:
            physics = friction_consistency(trend["vibration"], trend["temperature_rise"])
        else:
            physics = None
        self.last_physics = physics

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
        if self.last_trend_z is not None:
            if self.last_trend_z > TREND_ALERT:
                drift_floor = max(drift_floor, 0.78)
            elif self.last_trend_z > TREND_MONITOR:
                drift_floor = max(drift_floor, 0.58)
        if (
            self.last_physics is not None
            and self.last_physics > PHYSICS_CONSISTENCY_ALERT
            and self.last_trend_z is not None
            and TREND_MONITOR < self.last_trend_z <= TREND_ALERT
        ):
            drift_floor = max(drift_floor, 0.78)

        # Seasonal structure, vibration channel first. Reported for the
        # operator; it never votes (see model/seasonal.py for why not).
        vib_series = np.array([r["vibration_mm_s"] for r in readings], dtype=float)
        temp_series = np.array([r["temperature_c"] for r in readings], dtype=float)
        season = seasonal_period(vib_series)
        if season is None:
            season = seasonal_period(temp_series)

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
            # has moved furthest from how it normally wanders. An attribution,
            # not a limit ratio.
            contrib = max(trend.items(), key=lambda kv: abs(kv[1]))[0]
        else:
            contrib = "vibration"

        # Guide frequencies for the technician's handheld analyser, from the
        # series' median speed and an assumed common bearing. Approximate by
        # design; detection never depends on them.
        rpms = [float(r["rpm"]) for r in readings if r.get("rpm") not in (None,)]
        physics_hz: dict[str, float] | None = None
        assumed_bearing: str | None = None
        if rpms and max(rpms) > 0:
            try:
                raw_hz = defect_frequencies(float(np.median(rpms)), DEFAULT_BEARING)
                physics_hz = {k: round(v, 1) for k, v in raw_hz.items()}
                assumed_bearing = DEFAULT_BEARING
            except ValueError:
                physics_hz = None

        # Uncertainty on the driving displacement. A monitor verdict whose
        # interval includes zero is published as an abstention downstream.
        ci: list[float] | None = None
        if modeled:
            ci_col = {
                "vibration": I_VIB,
                "temperature_rise": I_TEMP,
                "pressure_variance": I_PRESS,
            }.get(contrib)
            if ci_col is not None:
                lo, hi = trend_ci(X[:TREND_OPENING, ci_col], X[-RECENT_WINDOW:, ci_col])
                ci = [round(lo, 2), round(hi, 2)]

        return {
            # 0..1 index of how far from baseline the machine has moved. Not a
            # probability, and named so that nobody reads it as one.
            "anomaly_index": round(agg_score, 3),
            "drift": round(drift, 4) if drift is not None else None,
            "trend_z": round(self.last_trend_z, 2) if self.last_trend_z is not None else None,
            "physics_consistency": round(physics, 3) if physics is not None else None,
            "physics_hz": physics_hz,
            "assumed_bearing": assumed_bearing,
            "seasonal_period": season,
            "trend_ci": ci,
            "conformal_set": prediction_set(
                _margins(self.last_drift, self.last_trend_z), CONFORMAL_DRIFT_Q95
            ),
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

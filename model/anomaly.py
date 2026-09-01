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

FEATURES = ("temperature_c", "vibration_mm_s", "pressure_bar",
            "vib_rolling_mean", "temp_rise", "pressure_variance_pct")


class BloomPulseAnomaly:
    """Single-use scorer. Construct one per series, because fitting is cheap
    and a shared instance would leak one series' baseline into the next
    request."""

    def __init__(self):
        # No scaler: the forest splits inside each feature's own range, so it
        # is scale invariant already. See tests/test_iforest.py.
        self.model = IsolationForest(n_estimators=150, random_state=42)

    def _features(self, readings: list[dict]) -> np.ndarray:
        """6-dim feature matrix, one row per reading. See FEATURES."""
        temps = np.array([r["temperature_c"] for r in readings], dtype=float)
        vibs = np.array([r["vibration_mm_s"] for r in readings], dtype=float)
        pressures = np.array(
            [r.get("pressure_bar") if r.get("pressure_bar") is not None else 5.0
             for r in readings], dtype=float)

        # centred rolling mean, window 5, clipped at the series edges
        vib_roll = np.array([vibs[max(0, i - 2):i + 3].mean() for i in range(len(vibs))])

        # temperature rise measured against the opening baseline
        baseline = float(temps[:MIN_BASELINE].mean())
        temp_rise = temps - baseline

        mean_pressure = float(pressures.mean())
        denom = abs(mean_pressure) if abs(mean_pressure) > 1e-6 else 1.0
        pressure_var = np.abs(pressures - mean_pressure) / denom * 100

        return np.column_stack([temps, vibs, pressures, vib_roll, temp_rise, pressure_var])

    def score(self, readings: list[dict]) -> dict:
        if not readings:
            raise ValueError("at least one reading is required")

        X = self._features(readings)

        # The forest only means something given a baseline it can learn a
        # shape from. Too few rows, or a flat baseline with no variance at
        # all, and it scores everything at roughly 0.5, which reads as
        # "monitor" for a perfectly healthy machine. In those cases the
        # threshold gates decide alone, starting from zero.
        fit_slice = X[:max(MIN_BASELINE, len(X) // 2)]
        modeled = len(X) >= MIN_BASELINE and bool(fit_slice.var(axis=0).max() > 1e-9)
        if modeled:
            # Fit on the opening slice, assuming a series starts healthy and
            # degrades from there.
            self.model.fit(fit_slice)
            # score_samples is already 0..1 with higher meaning more anomalous.
            scored = self.model.score_samples(X)
            agg_score = float(scored[-RECENT_WINDOW:].mean())
        else:
            agg_score = 0.0

        recent = X[-RECENT_WINDOW:]
        max_vib = float(recent[:, 1].max())
        max_temp_rise = float(recent[:, 4].max())
        pressure_var = float(recent[:, 5].max())

        # Physical threshold gates. A real breach floors the score.
        if max_vib > VIB_ALERT:
            agg_score = max(agg_score, 0.82)
        elif max_vib > VIB_NORMAL:
            agg_score = max(agg_score, 0.58)
        if max_temp_rise > TEMP_RISE_THRESHOLD:
            agg_score = max(agg_score, 0.78)
        if pressure_var > PRESSURE_VARIANCE_ALERT:
            agg_score = max(agg_score, 0.71)

        agg_score = float(np.clip(agg_score, 0.0, 1.0))
        failure_prob = float(np.clip(agg_score * 0.95 + 0.05 * (max_vib / 6.0), 0.0, 1.0))

        if agg_score < 0.50:
            severity, days = "normal", None
        elif agg_score < 0.65:
            severity, days = "monitor", 14
        elif agg_score < 0.82:
            severity, days = "alert", 7
        else:
            severity, days = "critical", 3

        # Compare each driver as a fraction of its own threshold. Comparing
        # raw values would pit mm/s against degrees against percent.
        contrib = max(
            {"vibration": max_vib / VIB_ALERT,
             "temperature_rise": max_temp_rise / TEMP_RISE_THRESHOLD,
             "pressure_variance": pressure_var / PRESSURE_VARIANCE_ALERT}.items(),
            key=lambda kv: kv[1],
        )[0]

        return {
            "anomaly_score": round(agg_score, 3),
            "failure_probability_7d": round(failure_prob, 3),
            "predicted_failure_days": days,
            "severity": severity,
            "contributing_feature": contrib,
            "baseline_modeled": modeled,
            "reading_count": len(readings),
            "metrics": {
                "max_vib": round(max_vib, 3),
                "max_temp_rise": round(max_temp_rise, 3),
                "pressure_var": round(pressure_var, 2),
            },
        }


def score_readings(readings: list[dict]) -> dict:
    """Score one series. Fresh engine per call, see BloomPulseAnomaly."""
    return BloomPulseAnomaly().score(readings)

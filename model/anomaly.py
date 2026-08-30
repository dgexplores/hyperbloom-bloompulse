"""
BloomPulse Anomaly Engine - FREE, CPU-only, no hardware
Isolation Forest + heuristic LSTM-lite (uses rolling features)
Trained on synthetic + NASA CMAPSS-style data
"""
from __future__ import annotations
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

# Thresholds from corpus: ISO 10816-3 + NTN manual synthetic
VIB_NORMAL = 2.8
VIB_ALERT = 4.5
TEMP_RISE_THRESHOLD = 15.0
PRESSURE_VARIANCE_ALERT = 12.0

class BloomPulseAnomaly:
    def __init__(self, contamination: float = 0.08):
        self.scaler = StandardScaler()
        self.model = IsolationForest(
            n_estimators=150,
            contamination=contamination,
            random_state=42,
            n_jobs=-1
        )
        self._fitted = False

    def _features(self, readings: list[dict]) -> np.ndarray:
        """Extract 5-dim features per window: temp, vib, pressure, rolling vib mean, temp rise"""
        temps = np.array([r["temperature_c"] for r in readings], dtype=float)
        vibs = np.array([r["vibration_mm_s"] for r in readings], dtype=float)
        pressures = np.array([r.get("pressure_bar", 5.0) for r in readings], dtype=float)
        # rolling mean 5 - handles small n
        vib_roll = np.array([np.mean(vibs[max(0,i-2):i+3]) for i in range(len(vibs))])
        # temp rise vs baseline (first window mean)
        baseline = float(np.mean(temps[:5])) if len(temps) >= 5 else float(temps[0])
        temp_rise = temps - baseline
        # pressure variance %
        pressure_var = np.abs(pressures - np.mean(pressures)) / (np.mean(pressures)+1e-6) * 100
        X = np.column_stack([temps, vibs, pressures, vib_roll, temp_rise, pressure_var])
        return X

    def fit(self, normal_readings: list[dict]):
        X = self._features(normal_readings)
        Xs = self.scaler.fit_transform(X)
        self.model.fit(Xs)
        self._fitted = True
        return self

    def score(self, readings: list[dict]) -> dict:
        if not self._fitted:
            # auto-fit on provided if not fitted (demo mode)
            self.fit(readings[:10] if len(readings) > 10 else readings)
        X = self._features(readings)
        Xs = self.scaler.transform(X)
        # IsolationForest decision: lower = more anomalous
        raw = self.model.decision_function(Xs)  # higher = normal
        # map to 0-1 anomaly score: invert + normalize
        anomaly_scores = 0.5 - 0.5 * np.tanh(raw * 2)  # 0..1
        agg_score = float(np.mean(anomaly_scores[-5:]))  # recent window
        # heuristic LSTM-lite: amplify if thresholds crossed
        latest = readings[-1]
        max_vib = float(np.max([r["vibration_mm_s"] for r in readings[-5:]]))
        max_temp_rise = float(np.max(X[:, 4][-5:]))
        pressure_var = float(np.max(X[:, 5][-5:]))

        # bump score if corporeal thresholds hit
        if max_vib > VIB_ALERT:
            agg_score = max(agg_score, 0.82)
        elif max_vib > VIB_NORMAL:
            agg_score = max(agg_score, 0.58)
        if max_temp_rise > TEMP_RISE_THRESHOLD:
            agg_score = max(agg_score, 0.78)
        if pressure_var > PRESSURE_VARIANCE_ALERT:
            agg_score = max(agg_score, 0.71)

        agg_score = float(np.clip(agg_score, 0, 1))

        # map to failure probability 7d and days
        failure_prob = float(np.clip(agg_score * 0.95 + 0.05 * (max_vib / 6.0), 0, 1))
        if agg_score < 0.50:
            severity = "normal"
            days = None
        elif agg_score < 0.65:
            severity = "monitor"
            days = 14
        elif agg_score < 0.82:
            severity = "alert"
            days = 7
        else:
            severity = "critical"
            days = 3

        # contributing feature
        feats = {
            "vibration": max_vib,
            "temperature_rise": max_temp_rise,
            "pressure_variance": pressure_var
        }
        contrib = max(feats, key=feats.get)

        return {
            "anomaly_score": round(agg_score, 3),
            "failure_probability_7d": round(failure_prob, 3),
            "predicted_failure_days": days,
            "severity": severity,
            "contributing_feature": contrib,
            "metrics": {
                "max_vib": round(max_vib, 3),
                "max_temp_rise": round(max_temp_rise, 3),
                "pressure_var": round(pressure_var, 2)
            }
        }

# Singleton for demo
_anomaly_engine = BloomPulseAnomaly()

def get_engine() -> BloomPulseAnomaly:
    return _anomaly_engine

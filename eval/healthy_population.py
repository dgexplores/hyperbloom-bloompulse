"""A reproducible population of healthy machines.

Used by `eval/calibrate.py` to set the drift cuts, and by the test suite to
assert the healthy false-positive rate. It lives in one place on purpose: the
population the cuts are set from and the population they are checked against
must be the same one, or the check proves nothing.

A "healthy machine" here means: stationary, vibration inside ISO 10816-3 Zone
A/B (the B/C boundary is 2.8 mm/s), temperature well under the 75 C alert the
corpus quotes, and ordinary sensor noise on every channel. Nothing is drifting.
"""
from __future__ import annotations

import numpy as np

VIB_RANGE = (1.0, 2.6)      # mm/s, Zone B/C boundary is 2.8
TEMP_RANGE = (45.0, 70.0)   # C, the corpus alerts at 75 C continuous
PRESSURE = 5.0              # bar
LENGTH_RANGE = (20, 120)    # readings

TEMPERATURE_NOISE = 0.7     # C
VIBRATION_NOISE = 0.09      # mm/s
PRESSURE_NOISE = 0.05       # bar


def healthy_series(seed: int) -> list[dict]:
    """One healthy machine's readings. Deterministic in `seed`."""
    rng = np.random.default_rng(seed)
    length = int(rng.integers(*LENGTH_RANGE))
    vib = float(rng.uniform(*VIB_RANGE))
    temp = float(rng.uniform(*TEMP_RANGE))
    return [
        {
            "timestamp": f"2026-08-20T{i // 60:02d}:{i % 60:02d}:00",
            "equipment_id": "CAL-01",
            "temperature_c": float(temp + rng.normal(0, TEMPERATURE_NOISE)),
            "vibration_mm_s": float(max(0.1, vib + rng.normal(0, VIBRATION_NOISE))),
            "pressure_bar": float(PRESSURE + rng.normal(0, PRESSURE_NOISE)),
        }
        for i in range(length)
    ]


def population(size: int = 400) -> list[list[dict]]:
    return [healthy_series(seed) for seed in range(size)]

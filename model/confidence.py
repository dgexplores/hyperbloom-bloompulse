"""Uncertainty on the trend displacement.

`trend_ci` bootstraps the standardized mean shift between the opening and
recent windows: B resamples, fully vectorized, microseconds not seconds.
The pipeline uses it for one decision only — a monitor verdict whose
interval includes zero is published as an abstention, not a displacement.
"""
from __future__ import annotations

import numpy as np


def trend_ci(
    opening,
    recent,
    B: int = 1000,
    level: float = 0.95,
    seed: int = 0,
) -> tuple[float, float]:
    """Percentile bootstrap CI for (recent_mean - opening_mean) / opening_std.

    Returns (lo, hi). Standardized in the same units as the trend z the
    ensemble already votes on.
    """
    opening = np.asarray(opening, dtype=float)
    recent = np.asarray(recent, dtype=float)
    spread = float(opening.std())
    if spread <= 1e-9:
        return (0.0, 0.0)
    rng = np.random.default_rng(seed)
    boot_o = opening[rng.integers(0, len(opening), size=(B, len(opening)))].mean(axis=1)
    boot_r = recent[rng.integers(0, len(recent), size=(B, len(recent)))].mean(axis=1)
    shifts = (boot_r - boot_o) / spread
    tail = (1.0 - level) / 2.0 * 100.0
    return (float(np.percentile(shifts, tail)), float(np.percentile(shifts, 100.0 - tail)))

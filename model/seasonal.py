"""Seasonal structure detection.

A periodic signal sampled over part of its cycle aliases into a false
displacement under a pure mean comparison. A cycle is only identifiable
when the series spans enough of it, so this module detects and reports
rather than corrects:

- a clear autocorrelation local maximum at lag p (2 < p < 24) -> p,
  reported in the verdict for the operator (check against the shift
  schedule).- anything longer -> None. It cannot be separated from drift inside one
  series, and suppressing the verdict on a guess would mask real failures.
  The boundary is locked by tests/test_seasonal.py instead.
"""
from __future__ import annotations

import numpy as np

MIN_LENGTH = 8
MAX_LAG = 24
PEAK_CUT = 0.7


def seasonal_period(x) -> int | None:
    """Dominant period of a series, or None.

    Linear-detrended normalized autocorrelation over lags 1..min(24, n-2);
    the smallest lag above 1 that is a local maximum clearing 0.7 wins.
    The local-maximum requirement is the whole trick: mere smoothness
    correlates strongly at short lags but decays monotonically, while a
    true cycle rises back to a peak at its period.
    """
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < MIN_LENGTH:
        return None
    t = np.arange(n)
    slope, intercept = np.polyfit(t, x, 1)
    resid = x - (slope * t + intercept)
    var = float(resid.var())
    if var <= 1e-12:
        return None
    resid = resid / float(np.sqrt(var))
    max_lag = min(MAX_LAG, n - 2)
    if max_lag < 3:
        return None
    corr = {
        lag: float((resid[: n - lag] * resid[lag:]).mean())
        for lag in range(1, max_lag + 1)
    }
    for lag in range(2, max_lag):
        if (
            corr[lag] > PEAK_CUT
            and corr[lag] > corr[lag - 1]
            and corr[lag] >= corr[lag + 1]
        ):
            return lag
    return None

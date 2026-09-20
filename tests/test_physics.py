"""Tests for the physics instrument (model/physics.py).

Two things: bearing defect frequencies from first principles, and a
friction-consistency score (heat + vibration moving together) that votes in
the ensemble alongside the forest and the trend test.
"""
import math

import pytest

from model.physics import (
    BEARING_GEOMETRY,
    UnknownBearingError,
    defect_frequencies,
    friction_consistency,
)


def test_geometry_table_covers_common_types():
    for bearing in ("6205", "6206", "6207", "6305", "6306", "NU205", "NU206"):
        geom = BEARING_GEOMETRY[bearing]
        assert geom["n"] > 0
        assert geom["d"] > 0
        assert geom["D"] > geom["d"]
        assert 0 <= geom["theta"] < math.pi / 2


def test_unknown_bearing_raises():
    with pytest.raises(UnknownBearingError):
        defect_frequencies(1750, "FAKE-9999")


def test_nonpositive_rpm_raises():
    with pytest.raises(ValueError):
        defect_frequencies(0, "6205")
    with pytest.raises(ValueError):
        defect_frequencies(-100, "6205")


def test_bpfo_plus_bpfi_equals_n_times_shaft_rate():
    """Algebraic identity of the defect formulas, independent of constants."""
    for bearing, geom in BEARING_GEOMETRY.items():
        for rpm in (900, 1750, 3600):
            freqs = defect_frequencies(rpm, bearing)
            fr = rpm / 60.0
            assert freqs["bpfo"] + freqs["bpfi"] == pytest.approx(geom["n"] * fr, rel=1e-9), bearing


def test_hand_computed_6205_at_1750rpm():
    """Independent hand computation for 6205 (n=9, d=7.938, D=38.5, theta=0)."""
    freqs = defect_frequencies(1750, "6205")
    fr = 1750 / 60.0
    ratio = 7.938 / 38.5
    assert freqs["shaft"] == pytest.approx(fr, rel=1e-9)
    assert freqs["bpfo"] == pytest.approx(4.5 * fr * (1 - ratio), rel=1e-6)
    assert freqs["bpfi"] == pytest.approx(4.5 * fr * (1 + ratio), rel=1e-6)
    # Cage turns slower than the shaft, balls spin faster than both.
    assert 0 < freqs["ftf"] < fr < freqs["bsf"]


def test_frequencies_scale_linearly_with_rpm():
    slow = defect_frequencies(900, "6305")
    fast = defect_frequencies(1800, "6305")
    for key in ("bpfo", "bpfi", "bsf", "ftf", "shaft"):
        assert fast[key] == pytest.approx(2 * slow[key], rel=1e-9)


def test_consistency_agreement_tends_to_one():
    assert friction_consistency(12.0, 8.0) > 0.9
    assert friction_consistency(20.0, 15.0) > 0.95


def test_consistency_conflict_tends_to_zero():
    assert friction_consistency(12.0, -8.0) < 0.1
    assert friction_consistency(-15.0, 10.0) < 0.05


def test_consistency_neutral_at_rest():
    assert friction_consistency(0.0, 0.0) == pytest.approx(0.5)


def test_consistency_symmetric_in_sign():
    assert friction_consistency(10.0, 6.0) == pytest.approx(friction_consistency(-10.0, -6.0))
    assert friction_consistency(10.0, -6.0) == pytest.approx(friction_consistency(-10.0, 6.0))


def test_consistency_bounded():
    import random
    rng = random.Random(42)
    for _ in range(200):
        c = friction_consistency(rng.uniform(-30, 30), rng.uniform(-30, 30))
        assert 0.0 <= c <= 1.0

"""Third instrument: physics the first two cannot see.

The Isolation Forest sees erratic channels and the trend test sees displaced
channels, but neither knows *why* heat and vibration move. Friction turns
motion into heat, so a vibration displacement with a matching temperature
displacement is machine evidence; a vibration displacement alone is as likely
a sensor. `friction_consistency` scores that agreement.

`defect_frequencies` is not a detector (the input has no spectra) but a guide:
the BPFO/BPFI/BSF/FTF a technician should check with a handheld analyser,
printed into the work order. Geometry values are typical catalogue figures,
approximate by design, and labelled as such wherever they surface.
"""
from __future__ import annotations

import math


class UnknownBearingError(KeyError):
    """Bearing type has no geometry row."""


# Typical rolling-element counts and dimensions (mm). Approximate catalogue
# figures for guidance frequencies, never for detection thresholds.
BEARING_GEOMETRY: dict[str, dict[str, float]] = {
    "6205": {"n": 9, "d": 7.938, "D": 38.5, "theta": 0.0},
    "6206": {"n": 9, "d": 9.525, "D": 46.0, "theta": 0.0},
    "6207": {"n": 9, "d": 11.112, "D": 53.5, "theta": 0.0},
    "6305": {"n": 7, "d": 11.906, "D": 43.5, "theta": 0.0},
    "6306": {"n": 8, "d": 12.7, "D": 51.0, "theta": 0.0},
    "NU205": {"n": 12, "d": 7.5, "D": 38.5, "theta": 0.0},
    "NU206": {"n": 12, "d": 9.0, "D": 46.0, "theta": 0.0},
}

DEFAULT_BEARING = "6205"

# Agreement steepness. At k=25 a (12, 8) displacement scores 0.98 and a
# (20, 15) scores ~1.0, while opposing signs collapse toward 0.
_CONSISTENCY_K = 25.0

# Escalation cut. Measured, not chosen: the healthy population peaks at 0.52
# (mean 0.50), so 0.9 sits in a wide empty band. See eval/calibrate.py.
PHYSICS_CONSISTENCY_ALERT = 0.9


def defect_frequencies(rpm: float, bearing: str = DEFAULT_BEARING) -> dict[str, float]:
    """Bearing defect frequencies in Hz for a shaft speed and bearing type.

    BPFO/BPFI: outer/inner race. BSF: rolling-element spin. FTF: cage.
    """
    if rpm <= 0:
        raise ValueError(f"rpm must be positive, got {rpm}")
    try:
        geom = BEARING_GEOMETRY[bearing]
    except KeyError:
        raise UnknownBearingError(f"no geometry for bearing {bearing!r}") from None
    n, d, D, theta = geom["n"], geom["d"], geom["D"], geom["theta"]
    fr = rpm / 60.0
    ratio = (d / D) * math.cos(theta)
    return {
        "shaft": fr,
        "bpfo": (n / 2.0) * fr * (1 - ratio),
        "bpfi": (n / 2.0) * fr * (1 + ratio),
        "bsf": (D / (2.0 * d)) * fr * (1 - ratio * ratio),
        "ftf": (fr / 2.0) * (1 - ratio),
    }


def friction_consistency(vib_z: float, temp_z: float) -> float:
    """Agreement between vibration and temperature displacement, 0..1.

    Same direction and large both ways tends to 1 (friction evidence);
    opposing directions tend to 0 (sensor-suspect); stillness is 0.5.
    """
    return 1.0 / (1.0 + math.exp(-(vib_z * temp_z) / _CONSISTENCY_K))

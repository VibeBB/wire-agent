"""Reference wire and connector specification tables.

Values are reference approximations drawn from ISO 6722 / LV112, JASO D611,
AVS/AVSS, FLRY, and TXL class behaviour; project contracts may override any
row inline. They are not a substitute for a manufacturer datasheet.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise


@dataclass(frozen=True)
class WireSpecRow:
    """Reference row for one wire type at one gauge."""

    name: str
    spec: str
    gauge_mm2: float
    outer_diameter_mm: float
    resistance_ohm_per_km: float
    ampacity_a: float  # at reference_temp_c, single wire in free air
    reference_temp_c: float
    insulation_rating_v: float
    insulation_temp_c: float
    min_bend_factor: float  # multiplier on outer_diameter_mm
    flex_class: str


# Approximate bundling derating (single wire in free air = 1.0), indexed by
# number of load-carrying wires sharing one route/bundle. Reference shape
# follows JASO D611 / ISO 6722 bundling guidance.
def bundle_derating(bundle_size: int) -> float:
    if bundle_size <= 1:
        return 1.0
    if bundle_size == 2:
        return 0.80
    if bundle_size == 3:
        return 0.70
    if bundle_size <= 5:
        return 0.60
    if bundle_size <= 8:
        return 0.55
    if bundle_size <= 12:
        return 0.50
    return 0.45


# Piecewise-linear ambient derating for a PVC-class insulation referenced
# at 80 °C (values above the reference are clipped to 0 in gates — the wire
# is out of class, not merely derated).
_AVSS_DERATING: tuple[tuple[float, float], ...] = (
    (80.0, 1.0),
    (90.0, 0.85),
    (100.0, 0.65),
    (105.0, 0.0),
)

_FLRY_DERATING: tuple[tuple[float, float], ...] = (
    (105.0, 1.0),
    (115.0, 0.75),
    (125.0, 0.0),
)

_TXL_DERATING: tuple[tuple[float, float], ...] = (
    (125.0, 1.0),
    (135.0, 0.75),
    (150.0, 0.0),
)


def temperature_factor(points: list[tuple[float, float]], ambient_c: float) -> float | None:
    """Interpolated derating factor at ambient_c; None if out of range."""
    if not points:
        return None
    ordered = sorted(points)
    if ambient_c < ordered[0][0]:
        return ordered[0][1]
    if ambient_c > ordered[-1][0]:
        return ordered[-1][1]
    for (t0, f0), (t1, f1) in pairwise(ordered):
        if t0 <= ambient_c <= t1:
            if t1 == t0:
                return f1
            return f0 + (f1 - f0) * (ambient_c - t0) / (t1 - t0)
    return ordered[-1][1]


WIRE_SPECS: dict[str, WireSpecRow] = {
    "AVSS-0.3": WireSpecRow(
        "AVSS 0.3", "AVSS", 0.3, 1.9, 52.0, 7.0, 80.0, 60.0, 105.0, 4.0, "static"
    ),
    "AVSS-0.5": WireSpecRow(
        "AVSS 0.5", "AVSS", 0.5, 2.0, 32.7, 12.7, 80.0, 60.0, 105.0, 4.0, "static"
    ),
    "AVSS-0.85": WireSpecRow(
        "AVSS 0.85", "AVSS", 0.85, 2.2, 20.8, 16.9, 80.0, 60.0, 105.0, 4.0, "static"
    ),
    "AVSS-1.25": WireSpecRow(
        "AVSS 1.25", "AVSS", 1.25, 2.4, 14.3, 22.7, 80.0, 60.0, 105.0, 4.0, "static"
    ),
    "AVSS-2.0": WireSpecRow(
        "AVSS 2.0", "AVSS", 2.0, 2.9, 8.81, 31.3, 80.0, 60.0, 105.0, 4.0, "static"
    ),
    "FLRY-B-0.35": WireSpecRow(
        "FLRY-B 0.35", "FLRY-B", 0.35, 1.3, 52.0, 7.0, 105.0, 60.0, 105.0, 4.0, "static"
    ),
    "FLRY-B-0.5": WireSpecRow(
        "FLRY-B 0.5", "FLRY-B", 0.5, 1.6, 37.1, 9.0, 105.0, 60.0, 105.0, 4.0, "static"
    ),
    "FLRY-B-0.75": WireSpecRow(
        "FLRY-B 0.75", "FLRY-B", 0.75, 1.9, 24.7, 12.0, 105.0, 60.0, 105.0, 4.0, "static"
    ),
    "FLRY-B-1.0": WireSpecRow(
        "FLRY-B 1.0", "FLRY-B", 1.0, 2.1, 18.5, 15.0, 105.0, 60.0, 105.0, 4.0, "static"
    ),
    "FLRY-B-1.5": WireSpecRow(
        "FLRY-B 1.5", "FLRY-B", 1.5, 2.4, 12.7, 19.0, 105.0, 60.0, 105.0, 4.0, "static"
    ),
    "FLRY-B-2.5": WireSpecRow(
        "FLRY-B 2.5", "FLRY-B", 2.5, 3.0, 7.6, 26.0, 105.0, 60.0, 105.0, 4.0, "static"
    ),
    "TXL-18AWG": WireSpecRow(
        "TXL 18AWG", "TXL", 0.82, 2.1, 23.0, 15.0, 125.0, 60.0, 125.0, 4.0, "static"
    ),
    "TXL-16AWG": WireSpecRow(
        "TXL 16AWG", "TXL", 1.31, 2.4, 14.6, 20.0, 125.0, 60.0, 125.0, 4.0, "static"
    ),
    "TXL-14AWG": WireSpecRow(
        "TXL 14AWG", "TXL", 2.08, 2.8, 8.96, 27.0, 125.0, 60.0, 125.0, 4.0, "static"
    ),
}

SPEC_DERATING: dict[str, tuple[tuple[float, float], ...]] = {
    "AVSS": _AVSS_DERATING,
    "AVS": _AVSS_DERATING,
    "FLRY-B": _FLRY_DERATING,
    "FLRY": _FLRY_DERATING,
    "TXL": _TXL_DERATING,
}

# Connector family hints used to prefill contracts during intake. Ratings
# are catalog-typical; the contract record itself is the authority.
CONNECTOR_FAMILIES: dict[str, dict[str, object]] = {
    "JST XH": {
        "rated_current_a": 3.0,
        "rated_voltage_v": 250.0,
        "accepts_mm2": (0.08, 0.5),
        "mating_cycles": 30,
        "sealed": False,
    },
    "JST PH": {
        "rated_current_a": 2.0,
        "rated_voltage_v": 100.0,
        "accepts_mm2": (0.05, 0.22),
        "mating_cycles": 30,
        "sealed": False,
    },
    "Molex Micro-Fit": {
        "rated_current_a": 5.0,
        "rated_voltage_v": 250.0,
        "accepts_mm2": (0.2, 0.52),
        "mating_cycles": 30,
        "sealed": False,
    },
    "Molex Mini-Fit Jr": {
        "rated_current_a": 9.0,
        "rated_voltage_v": 600.0,
        "accepts_mm2": (0.33, 2.08),
        "mating_cycles": 30,
        "sealed": False,
    },
    "Deutsch DT": {
        "rated_current_a": 13.0,
        "rated_voltage_v": 250.0,
        "accepts_mm2": (0.35, 1.5),
        "mating_cycles": 100,
        "sealed": True,
    },
    "TE Superseal 1.5": {
        "rated_current_a": 14.0,
        "rated_voltage_v": 250.0,
        "accepts_mm2": (0.35, 1.5),
        "mating_cycles": 25,
        "sealed": True,
    },
}

DEFAULT_VOLTAGE_DROP_FRACTION = 0.03

"""Test-design suite for the deterministic gates (docs/test-coverage.md).

Each relational guard is pinned with 3-value boundary analysis (just below,
on, just above the limit, via ``math.nextafter``), Boolean guards with
decision tables that give every condition an MC/DC independence pair, and
the pure derating tables with properties checked exhaustively over their
integer domain and over a dense float grid that includes every breakpoint.
"""

from __future__ import annotations

import math
from typing import Any

import pytest
from pydantic import ValidationError

from helpers import example_contract_data
from wire.contract import CavitySpec, HarnessConnector, HarnessContract
from wire.gates import run_gates
from wire.standards import SPEC_DERATING, bundle_derating, temperature_factor

UP = math.inf
DOWN = -math.inf


def _statuses(data: dict[str, Any], check_id: str, item: str | None = None) -> list[str]:
    report = run_gates(HarnessContract.model_validate(data))
    return [
        c.status for c in report.checks if c.id == check_id and (item is None or c.subject == item)
    ]


def _wire(data: dict[str, Any], wire_id: str) -> dict[str, Any]:
    return next(w for w in data["wires"] if w["id"] == wire_id)


def _net(data: dict[str, Any], net_id: str) -> dict[str, Any]:
    return next(n for n in data["nets"] if n["id"] == net_id)


def _wire_type(data: dict[str, Any], type_id: str) -> dict[str, Any]:
    return next(t for t in data["wire_types"] if t["id"] == type_id)


# --- standards: bundle derating table (equivalence classes + boundaries) ---


@pytest.mark.parametrize(
    ("size", "factor"),
    [
        (0, 1.0),
        (1, 1.0),
        (2, 0.80),
        (3, 0.70),
        (4, 0.60),
        (5, 0.60),
        (6, 0.55),
        (8, 0.55),
        (9, 0.50),
        (12, 0.50),
        (13, 0.45),
        (100, 0.45),
    ],
)
def test_bundle_derating_class_edges(size: int, factor: float) -> None:
    assert bundle_derating(size) == factor


def test_bundle_derating_is_monotone_and_bounded() -> None:
    for size in range(201):
        here = bundle_derating(size)
        assert 0.45 <= here <= 1.0
        assert bundle_derating(size + 1) <= here


# --- standards: piecewise-linear temperature factor ---

_CURVE = [(80.0, 1.0), (90.0, 0.85), (100.0, 0.65), (105.0, 0.0)]


def test_temperature_factor_empty_curve_is_unknown() -> None:
    assert temperature_factor([], 25.0) is None


@pytest.mark.parametrize(
    ("ambient", "expected"),
    [
        (math.nextafter(80.0, DOWN), 1.0),
        (80.0, 1.0),
        (85.0, 0.925),
        (90.0, 0.85),
        (105.0, 0.0),
        (math.nextafter(105.0, UP), 0.0),
        (200.0, 0.0),
        (-40.0, 1.0),
    ],
)
def test_temperature_factor_edges_and_interpolation(ambient: float, expected: float) -> None:
    assert temperature_factor(_CURVE, ambient) == pytest.approx(expected)


def test_temperature_factor_duplicate_breakpoint_uses_first_sorted_segment() -> None:
    assert temperature_factor([(80.0, 1.0), (80.0, 0.5), (90.0, 0.0)], 80.0) == 1.0
    assert temperature_factor([(80.0, 1.0), (90.0, 0.7), (90.0, 0.2)], 90.0) == pytest.approx(0.2)


_GRID = sorted({t / 4 for t in range(-240, 801)} | {t for t, _ in _CURVE})


def test_temperature_factor_stays_within_curve_range_and_never_rises() -> None:
    previous = math.inf
    for ambient in _GRID:
        factor = temperature_factor(_CURVE, ambient)
        assert factor is not None
        assert 0.0 <= factor <= 1.0
        assert factor <= previous + 1e-12
        previous = factor


# --- contract validators (fail closed at the schema boundary) ---


@pytest.mark.parametrize(
    ("accepts", "ok"),
    [
        ((0.0, 0.5), False),
        ((-0.1, 0.5), False),
        ((math.nextafter(0.0, UP), 0.5), True),
        ((0.5, 0.5), True),
        ((0.5, math.nextafter(0.5, DOWN)), False),
        ((0.5, 0.75), True),
    ],
)
def test_cavity_accepts_range_boundaries(accepts: tuple[float, float], ok: bool) -> None:
    if ok:
        assert CavitySpec(id="1", accepts_mm2=accepts).accepts_mm2 == accepts
    else:
        with pytest.raises(ValidationError):
            CavitySpec(id="1", accepts_mm2=accepts)


def _connector(**overrides: Any) -> dict[str, Any]:
    data = example_contract_data()["connectors"][0]
    data.update(overrides)
    return data


@pytest.mark.parametrize(("count", "ok"), [(3, False), (4, True), (5, True), (None, True)])
def test_connector_cavity_count_boundary(count: int | None, ok: bool) -> None:
    data = _connector(cavity_count=count)
    assert len(data["cavities"]) == 4
    if ok:
        HarnessConnector.model_validate(data)
    else:
        with pytest.raises(ValidationError, match="cavity_count"):
            HarnessConnector.model_validate(data)


def test_connector_duplicate_cavity_ids_rejected() -> None:
    data = _connector()
    data["cavities"][1]["id"] = data["cavities"][0]["id"]
    with pytest.raises(ValidationError, match="unique"):
        HarnessConnector.model_validate(data)


# --- gates: ampacity ---


def _exact_ampacity_limit(data: dict[str, Any], wire_id: str) -> float:
    contract = HarnessContract.model_validate(data)
    wire = next(w for w in contract.wires if w.id == wire_id)
    wtype = contract.wire_type_map()[wire.wire_type]
    curve = [(p.temperature_c, p.factor) for p in wtype.temp_derating]
    if not curve and wtype.spec:
        curve = list(SPEC_DERATING.get(wtype.spec, []))
    factor = temperature_factor(curve, contract.ambient_temperature_c)
    assert factor is not None
    bundle = sum(1 for w in contract.wires if w.route == wire.route)
    return wtype.ampacity_a * factor * bundle_derating(bundle)


@pytest.mark.parametrize(("step", "status"), [(DOWN, "pass"), (0.0, "pass"), (UP, "fail")])
def test_ampacity_three_value_boundary(step: float, status: str) -> None:
    data = example_contract_data()
    limit = _exact_ampacity_limit(data, "W3")
    _net(data, "N3")["current_a"] = limit if step == 0.0 else math.nextafter(limit, step)
    assert _statuses(data, "ampacity", "W3") == [status]


def _no_curve(data: dict[str, Any], type_id: str) -> dict[str, Any]:
    wtype = _wire_type(data, type_id)
    wtype["temp_derating"] = []
    wtype["spec"] = None
    return wtype


@pytest.mark.parametrize(
    ("delta", "status"),
    [(DOWN, "pass"), (0.0, "pass"), (UP, "unknown")],
)
def test_ampacity_without_curve_is_unknown_above_reference(delta: float, status: str) -> None:
    data = example_contract_data()
    wtype = _no_curve(data, "WT1")
    reference = wtype["reference_temp_c"]
    data["ambient_temperature_c"] = reference if delta == 0.0 else math.nextafter(reference, delta)
    statuses = _statuses(data, "ampacity", "W1")
    assert statuses == [status]


@pytest.mark.parametrize(("ambient", "status"), [(100.0, "pass"), (105.0, "fail"), (130.0, "fail")])
def test_ampacity_fails_where_curve_reaches_zero(ambient: float, status: str) -> None:
    data = example_contract_data()
    data["ambient_temperature_c"] = ambient
    assert _statuses(data, "ampacity", "W1") == [status]


# --- gates: voltage drop ---


def _drop(data: dict[str, Any], wire_id: str) -> float:
    wire = _wire(data, wire_id)
    net = _net(data, wire["net"])
    wtype = _wire_type(data, wire["wire_type"])
    return net["current_a"] * (wire["length_m"] / 1000.0) * wtype["resistance_ohm_per_km"]


@pytest.mark.parametrize(("step", "status"), [(UP, "pass"), (0.0, "pass"), (DOWN, "fail")])
def test_voltage_drop_three_value_boundary(step: float, status: str) -> None:
    data = example_contract_data()
    drop = _drop(data, "W3")
    net = _net(data, "N3")
    net["max_voltage_drop_v"] = drop if step == 0.0 else math.nextafter(drop, step)
    assert _statuses(data, "voltage_drop", "W3") == [status]


def test_voltage_drop_zero_volt_net_needs_explicit_limit() -> None:
    data = example_contract_data()
    net = _net(data, "N2")
    assert net["voltage_v"] == 0.0
    net.pop("max_voltage_drop_v")
    assert _statuses(data, "voltage_drop", "W2") == ["unknown"]


def test_voltage_drop_default_fraction_applies_above_zero_volts() -> None:
    data = example_contract_data()
    net = _net(data, "N1")
    assert "max_voltage_drop_v" not in net
    assert _statuses(data, "voltage_drop", "W1") == ["pass"]
    net["voltage_v"] = math.nextafter(0.0, UP)
    assert _statuses(data, "voltage_drop", "W1") == ["fail"]


# --- gates: insulation rating decision table (voltage_ok x temp_ok) ---


@pytest.mark.parametrize(
    ("voltage_ok", "temp_ok", "status"),
    [
        (True, True, "pass"),
        (False, True, "fail"),
        (True, False, "fail"),
        (False, False, "fail"),
    ],
)
def test_insulation_rating_decision_table(voltage_ok: bool, temp_ok: bool, status: str) -> None:
    data = example_contract_data()
    wtype = _wire_type(data, "WT1")
    net = _net(data, "N1")
    net["voltage_v"] = (
        wtype["insulation_rating_v"]
        if voltage_ok
        else math.nextafter(wtype["insulation_rating_v"], UP)
    )
    data["ambient_temperature_c"] = (
        wtype["insulation_temp_c"] if temp_ok else math.nextafter(wtype["insulation_temp_c"], UP)
    )
    assert _statuses(data, "insulation_rating", "W1") == [status]


# --- gates: connector rating ---


def _connector_status(data: dict[str, Any], connector_id: str = "C1") -> list[str]:
    return _statuses(data, "connector_rating", connector_id)


@pytest.mark.parametrize(("step", "status"), [(UP, "pass"), (0.0, "pass"), (DOWN, "fail")])
def test_connector_current_three_value_boundary(step: float, status: str) -> None:
    data = example_contract_data()
    peak = max(n["current_a"] for n in data["nets"])
    data["connectors"][0]["rated_current_a"] = peak if step == 0.0 else math.nextafter(peak, step)
    assert _connector_status(data) == [status]


@pytest.mark.parametrize(("step", "status"), [(UP, "pass"), (0.0, "pass"), (DOWN, "fail")])
def test_connector_voltage_three_value_boundary(step: float, status: str) -> None:
    data = example_contract_data()
    peak = max(n["voltage_v"] for n in data["nets"])
    data["connectors"][0]["rated_voltage_v"] = peak if step == 0.0 else math.nextafter(peak, step)
    assert _connector_status(data) == [status]


@pytest.mark.parametrize(
    ("service", "status"),
    [
        (None, "pass"),
        ({}, "pass"),
        ({"mating_cycles": 29}, "pass"),
        ({"mating_cycles": 30}, "pass"),
        ({"mating_cycles": 31}, "fail"),
    ],
)
def test_connector_mating_cycles_decision_and_boundary(
    service: dict[str, int] | None, status: str
) -> None:
    data = example_contract_data()
    assert data["connectors"][0]["mating_cycles"] == 30
    if service is None:
        data.pop("service")
    else:
        data["service"] = service
    assert _connector_status(data) == [status]


@pytest.mark.parametrize(
    ("rating", "status"),
    [
        (None, "pass"),
        (math.nextafter(60.0, UP), "pass"),
        (60.0, "pass"),
        (math.nextafter(60.0, DOWN), "fail"),
    ],
)
def test_connector_temperature_decision_and_boundary(rating: float | None, status: str) -> None:
    data = example_contract_data()
    assert data["ambient_temperature_c"] == 60.0
    data["connectors"][0]["temp_rating_c"] = rating
    assert _connector_status(data) == [status]


@pytest.mark.parametrize(
    ("keyings", "status"),
    [
        (("A", "B"), None),
        (("A", "A"), "fail"),
        (("A", None), "unknown"),
        ((None, None), "unknown"),
    ],
)
def test_identical_housing_keying_decision_table(
    keyings: tuple[str | None, str | None], status: str | None
) -> None:
    data = example_contract_data()
    for connector, keying in zip(data["connectors"], keyings, strict=True):
        connector["keying"] = keying
    keyed = [s for s in _statuses(data, "connector_rating") if s != "pass"]
    assert keyed == ([] if status is None else [status])

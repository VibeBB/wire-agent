"""Test-design suite for the deterministic gates (docs/test-coverage.md).

Each relational guard is pinned with 3-value boundary analysis (just below,
on, just above the limit, via ``math.nextafter``), Boolean guards with
decision tables that give every condition an MC/DC independence pair, and
the pure derating tables with properties checked exhaustively over their
integer domain and over a dense float grid that includes every breakpoint.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from helpers import example_contract_data
from wire.contract import CavitySpec, HarnessConnector, HarnessContract
from wire.gates import GateCheck, GateReport, run_gates
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


# --- decision mutants: conditions only reachable past model validation ---
#
# The contract model already rejects unknown net/route/splice/connector
# references; the gates keep a fail-closed second layer for objects built
# without validation (model_construct, deserialized copies). Tests below
# mutate fields after model_validate to reach that layer.


def _report(data: dict[str, Any]) -> GateReport:
    return run_gates(HarnessContract.model_validate(data))


def _checks(report: GateReport, check_id: str) -> list[GateCheck]:
    return [c for c in report.checks if c.id == check_id]


def _pair_check(report: GateReport) -> GateCheck:
    return next(
        c
        for c in _checks(report, "shielding_pairing")
        if c.subject == "twisted-pair routing"
    )


def test_report_dict_counts_each_status_bucket() -> None:
    data = example_contract_data()
    data["nets"].append({"id": "N4", "signal_class": "power", "voltage_v": 1.0, "current_a": 0.0})
    _wire(data, "W1")["route"] = None
    report = _report(data)
    counts = report.to_dict(HarnessContract.model_validate(data))["summary"]
    expected = {
        status: sum(1 for c in report.checks if c.status == status)
        for status in ("pass", "fail", "unknown")
    }
    assert expected["fail"] >= 1  # netlist_coverage on the unwired net
    assert expected["unknown"] >= 1  # bend_radius route coverage
    assert counts == expected


def test_connectivity_flags_every_bad_reference() -> None:
    data = example_contract_data()
    contract = HarnessContract.model_validate(data)

    contract.wires[0].from_endpoint.splice = "SP9"
    assert "unknown splice SP9" in _checks(run_gates(contract), "connectivity")[0].detail
    contract.wires[0].from_endpoint.splice = None

    contract.wires[0].from_endpoint.connector = "C9"
    assert "unknown connector C9" in _checks(run_gates(contract), "connectivity")[0].detail
    contract.wires[0].from_endpoint.connector = "C1"

    contract.wires[0].from_endpoint.cavity = "9"
    assert "unknown cavity C1:9" in _checks(run_gates(contract), "connectivity")[0].detail
    contract.wires[0].from_endpoint.cavity = "1"

    contract.wires[0].route = "RT9"
    assert "unknown route RT9" in _checks(run_gates(contract), "connectivity")[0].detail
    contract.wires[0].route = "RT1"

    contract.wires[0].to_endpoint = contract.wires[0].from_endpoint
    assert "both endpoints identical" in _checks(run_gates(contract), "connectivity")[0].detail


def test_connectivity_skips_endpoint_without_connector_or_splice() -> None:
    data = example_contract_data()
    contract = HarnessContract.model_validate(data)
    contract.wires[0].from_endpoint.connector = None
    contract.wires[0].from_endpoint.cavity = None
    detail = _checks(run_gates(contract), "connectivity")[0].detail
    assert "W1" not in detail


def test_splice_legs_require_two_and_one_net() -> None:
    data = example_contract_data()
    data["splices"] = [{"id": "SP1"}, {"id": "SP2"}]
    contract = HarnessContract.model_validate(data)
    contract.wires[0].from_endpoint.splice = "SP1"
    contract.wires[1].from_endpoint.splice = "SP1"
    contract.wires[2].from_endpoint.splice = "SP2"
    checks = {c.subject: c for c in _checks(run_gates(contract), "splice_integrity")}
    # SP1 carries legs on nets N1 and N2 -> multi-net failure detail
    assert checks["SP1"].status == "fail"
    assert "span multiple nets" in checks["SP1"].detail
    # SP2 carries a single leg -> leg-count failure detail
    assert "1 leg(s)" in checks["SP2"].detail


def test_netlist_coverage_flags_unwired_net() -> None:
    data = example_contract_data()
    data["nets"].append({"id": "N4", "signal_class": "power", "voltage_v": 1.0, "current_a": 0.0})
    check = _checks(_report(data), "netlist_coverage")[0]
    assert check.status == "fail"
    assert "N4 has no wire" in check.detail


def test_shielding_flags_required_shield_and_pair_routes() -> None:
    data = example_contract_data()
    _net(data, "N1")["shield_required"] = True
    check = _checks(_report(data), "shielding_pairing")[0]
    assert check.status == "fail"
    assert "requires shield" in check.detail


def test_twisted_pair_checks_route_sharing() -> None:
    data = example_contract_data()
    _net(data, "N1")["twisted_pair_with"] = "N2"
    _net(data, "N2")["twisted_pair_with"] = "N1"
    check = _pair_check(_report(data))
    assert check.status == "pass"

    _wire(data, "W1")["route"] = "RT2"
    check = _pair_check(_report(data))
    assert check.status == "fail"
    assert "do not share one route" in check.detail

    data = example_contract_data()
    _net(data, "N1")["twisted_pair_with"] = "N2"
    _wire(data, "W1")["route"] = None
    check = _pair_check(_report(data))
    assert check.status == "fail"

    contract = HarnessContract.model_validate(example_contract_data())
    contract.nets[0].twisted_pair_with = "N9"
    check = _pair_check(run_gates(contract))
    assert check.status == "fail"
    assert "pair N9 unknown" in check.detail


def test_ampacity_declared_curve_wins_over_spec_table() -> None:
    data = example_contract_data()
    # WT1 declares both spec="AVSS" and an explicit curve: the explicit
    # curve must win (ambient 60C is below the 80C reference -> factor 1.0).
    report = _report(data)
    check = next(c for c in _checks(report, "ampacity") if c.subject == "W1")
    assert check.status == "pass"
    assert check.limit == round(12.7 * bundle_derating(2), 4)


def test_ampacity_no_curve_above_reference_is_unknown() -> None:
    data = example_contract_data()
    data["ambient_temperature_c"] = 85.0  # above WT1's 80C reference
    _wire_type(data, "WT1")["temp_derating"] = []
    _wire_type(data, "WT1")["spec"] = None
    check = next(c for c in _checks(_report(data), "ampacity") if c.subject == "W1")
    assert check.status == "unknown"
    assert "no derating curve" in check.detail


def test_ampacity_zero_factor_boundary_reports_curve() -> None:
    for ambient in (105.0, 110.0):
        data = example_contract_data()
        data["ambient_temperature_c"] = ambient
        check = next(c for c in _checks(_report(data), "ampacity") if c.subject == "W1")
        assert check.status == "fail"
        assert "ambient above derating curve" in check.detail


def test_ampacity_detail_marks_unrouted_wire() -> None:
    data = example_contract_data()
    _wire(data, "W1")["route"] = None
    check = next(c for c in _checks(_report(data), "ampacity") if c.subject == "W1")
    assert "route -" in check.detail


def test_bend_radius_flex_required_and_exact_boundary() -> None:
    data = example_contract_data()
    data["routes"][0]["flex_required"] = True
    fail_check = next(c for c in _checks(_report(data), "bend_radius") if c.subject == "RT1")
    assert fail_check.status == "fail"
    assert "requires flex" in fail_check.detail

    data = example_contract_data()
    data["routes"][0]["flex_required"] = True
    _wire_type(data, "WT1")["flex_class"] = "dynamic"
    assert not [
        c
        for c in _checks(_report(data), "bend_radius")
        if c.subject == "RT1" and "requires flex" in c.detail
    ]

    data = example_contract_data()
    data["routes"][0]["segments"][0]["min_bend_radius_mm"] = 8.0
    check = next(c for c in _checks(_report(data), "bend_radius") if c.subject == "RT1:S1")
    assert check.status == "pass"  # required is exactly 8.0 mm (4.0 x 2.0)


def test_segregation_route_connector_and_unrouted_scopes() -> None:
    data = example_contract_data()
    _wire(data, "W3")["route"] = "RT1"  # power + analog share RT1
    check = _checks(_report(data), "segregation")[0]
    assert check.status == "fail"
    assert "RT1: analog+power" in check.detail

    data = example_contract_data()
    _wire(data, "W3")["route"] = None
    check = _checks(_report(data), "segregation")[0]
    assert check.status == "unknown"
    assert "wires without route cannot be segregated" in check.detail

    data = example_contract_data()
    data["segregations"] = [{"classes": ["power", "analog"], "rule": "no_shared_connector"}]
    check = _checks(_report(data), "segregation")[0]
    assert check.status == "fail"
    assert "C1: analog+power" in check.detail


def test_segregation_ignores_splice_only_endpoints() -> None:
    data = example_contract_data()
    data["segregations"] = [{"classes": ["power", "analog"], "rule": "no_shared_connector"}]
    contract = HarnessContract.model_validate(data)
    # W1 (power) leaves both connectors through splices; only analog and
    # ground wires terminate at C1/C2, so no policy violation remains.
    contract.wires[0].from_endpoint.splice = "SP1"
    contract.wires[0].from_endpoint.connector = None
    contract.wires[0].from_endpoint.cavity = None
    contract.wires[0].to_endpoint.splice = "SP2"
    contract.wires[0].to_endpoint.connector = None
    contract.wires[0].to_endpoint.cavity = None
    check = _checks(run_gates(contract), "segregation")[0]
    assert check.status == "pass"


def test_terminal_compatibility_decision_branches() -> None:
    data = example_contract_data()
    _wire_type(data, "WT1")["gauge_mm2"] = 0.6
    check = next(
        c for c in _checks(_report(data), "terminal_compatibility") if c.subject == "W1:C1:1"
    )
    assert check.status == "fail"
    assert "gauge 0.6 outside" in check.detail

    data = example_contract_data()
    _wire(data, "W1")["terminal_a"] = "WRONG-TERM"
    check = next(
        c for c in _checks(_report(data), "terminal_compatibility") if c.subject == "W1:C1:1"
    )
    assert check.status == "fail"
    assert "terminal WRONG-TERM != cavity" in check.detail

    data = example_contract_data()
    _wire(data, "W1")["terminal_a"] = None
    check = next(
        c for c in _checks(_report(data), "terminal_compatibility") if c.subject == "W1:C1:1"
    )
    assert check.status == "unknown"
    assert "terminal not fully declared" in check.detail

    data = example_contract_data()
    contract = HarnessContract.model_validate(data)
    contract.connectors[0].cavities[0].terminal = None
    check = next(
        c for c in _checks(run_gates(contract), "terminal_compatibility") if c.subject == "W1:C1:1"
    )
    assert check.status == "unknown"


def test_terminal_compatibility_selects_the_declared_cavity() -> None:
    data = example_contract_data()
    # Second cavity with a tighter accepted range: the lookup must pick
    # cavity 1 (0.08-0.5) for a 0.35 mm2 wire, not cavity 9 (0.08-0.2).
    data["connectors"][0]["cavities"].append(
        {"id": "9", "accepts_mm2": [0.08, 0.2], "terminal": "SXH-001T-P0.6"}
    )
    _wire(data, "W3")["wire_type"] = "WT2"
    check = next(
        c for c in _checks(_report(data), "terminal_compatibility") if c.subject == "W3:C1:3"
    )
    assert check.status == "pass"


def test_connector_rating_counts_to_endpoint_and_count_boundary() -> None:
    data = example_contract_data()
    data["connectors"][1]["rated_current_a"] = 1.5
    contract = HarnessContract.model_validate(data)
    # W1 leaves C1 through a splice but still lands on C2 via to_endpoint.
    contract.wires[0].from_endpoint.splice = "SP1"
    contract.wires[0].from_endpoint.connector = None
    contract.wires[0].from_endpoint.cavity = None
    by_subject = {c.subject: c for c in _checks(run_gates(contract), "connector_rating")}
    assert by_subject["C2"].status == "fail"
    assert "current 2.0 A" in by_subject["C2"].detail

    data = example_contract_data()
    data["connectors"][0]["cavity_count"] = 4  # exactly len(cavities)
    by_subject = {c.subject: c for c in _checks(_report(data), "connector_rating")}
    assert by_subject["C1"].status == "pass"


def test_anchor_resolution_mech_presence_and_missing() -> None:
    data = example_contract_data()
    data["routes"][0]["anchors"] = ["A1", "A2"]
    data["imported_sources"] = [
        {"id": "I1", "system": "circuit", "ref": "x.json", "anchors": ["A1", "A2"]}
    ]
    check = _checks(_report(data), "anchor_resolution")[0]
    assert check.status == "unknown"
    assert "no mech envelope" in check.detail

    data["imported_sources"] = [
        {
            "id": "I1",
            "system": "mech",
            "ref": "x.json",
            "anchors": ["A1"],
            "anchor_points": [{"name": "A1", "position_mm": [0.0, 0.0, 0.0]}],
        }
    ]
    check = _checks(_report(data), "anchor_resolution")[0]
    assert check.status == "fail"
    assert "missing: A2" in check.detail

    data["imported_sources"] = [
        {
            "id": "I1",
            "system": "mech",
            "ref": "x.json",
            "anchors": ["A1", "A2"],
            "anchor_points": [
                {"name": "A1", "position_mm": [0.0, 0.0, 0.0]},
                {"name": "A2", "position_mm": [10.0, 0.0, 0.0]},
            ],
        }
    ]
    check = _checks(_report(data), "anchor_resolution")[0]
    assert check.status == "pass"


def test_route_geometry_boundaries_and_unplaced() -> None:
    data = example_contract_data()
    data["routes"][0]["anchors"] = ["A1", "A2"]
    data["imported_sources"] = [
        {
            "id": "I1",
            "system": "mech",
            "ref": "x.json",
            "anchors": ["A1", "A2"],
            "anchor_points": [
                {"name": "A1", "position_mm": [0.0, 0.0, 0.0]},
                {"name": "A2", "position_mm": [500.0, 0.0, 0.0]},
            ],
        }
    ]
    # RT1 segments total 0.5 m = 500 mm: exactly at the polyline span.
    check = _checks(_report(data), "route_geometry")[0]
    assert check.status == "pass"

    data["routes"][0]["segments"][1]["length_m"] = 0.1  # 400 mm < 500 mm
    check = _checks(_report(data), "route_geometry")[0]
    assert check.status == "fail"
    assert "route shorter than its anchor polyline" in check.detail

    data = example_contract_data()
    data["routes"][0]["anchors"] = ["A1", "A2"]
    data["imported_sources"] = [
        {
            "id": "I1",
            "system": "mech",
            "ref": "x.json",
            "anchors": ["A1", "A2"],
            "anchor_points": [
                {"name": "A1", "position_mm": [0.0, 0.0, 0.0]},
                {"name": "A2", "position_mm": None},
            ],
        }
    ]
    check = _checks(_report(data), "route_geometry")[0]
    assert check.status == "unknown"
    assert "anchors without position_mm: A2" in check.detail

    data = example_contract_data()
    data["routes"][0]["anchors"] = ["A1"]
    check = _checks(_report(data), "route_geometry")[0]
    assert check.status == "pass"
    assert "no route spans two anchors" in check.detail


def test_import_freshness_passes_fails_and_skips(tmp_path: Path) -> None:
    blob = tmp_path / "import.json"
    blob.write_bytes(b'{"ok": true}')
    import hashlib

    digest = hashlib.sha256(b'{"ok": true}').hexdigest()
    data = example_contract_data()
    data["imported_sources"] = [{"id": "I1", "system": "mech", "ref": str(blob), "sha256": digest}]
    check = _checks(_report(data), "import_freshness")[0]
    assert check.status == "pass"

    blob.write_bytes(b'{"tampered": true}')
    check = _checks(_report(data), "import_freshness")[0]
    assert check.status == "fail"
    assert "changed since import" in check.detail

    data["imported_sources"] = [
        {"id": "I1", "system": "mech", "ref": str(tmp_path / "missing.json"), "sha256": digest}
    ]
    check = _checks(_report(data), "import_freshness")[0]
    assert check.status == "unknown"

    data["imported_sources"] = [{"id": "I1", "system": "mech", "ref": str(blob)}]
    check = _checks(_report(data), "import_freshness")[0]
    assert check.status == "pass"
    assert "no hashed imports" in check.detail


def test_manifest_integrity_mismatches(tmp_path: Path) -> None:
    data = example_contract_data()
    contract = HarnessContract.model_validate(data)
    (tmp_path / "artifact.txt").write_bytes(b"payload")
    import hashlib
    import json

    from wire.contract import contract_sha256

    good = {
        "contract_sha256": contract_sha256(contract),
        "files": [
            {
                "path": "artifact.txt",
                "sha256": hashlib.sha256(b"payload").hexdigest(),
            }
        ],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(good), encoding="utf-8")
    report = run_gates(contract, out_dir=tmp_path)
    check = _checks(report, "manifest_integrity")[0]
    assert check.status == "pass"
    # every check passing (no fail or unknown) is what lets the verdict pass
    assert report.verdict == "pass"

    bad = dict(good)
    bad["contract_sha256"] = "0" * 64
    (tmp_path / "manifest.json").write_text(json.dumps(bad), encoding="utf-8")
    check = _checks(run_gates(contract, out_dir=tmp_path), "manifest_integrity")[0]
    assert check.status == "fail"
    assert "contract_sha256 mismatch" in check.detail

    bad = json.loads(json.dumps(good))
    bad["files"][0]["sha256"] = "0" * 64
    (tmp_path / "manifest.json").write_text(json.dumps(bad), encoding="utf-8")
    check = _checks(run_gates(contract, out_dir=tmp_path), "manifest_integrity")[0]
    assert check.status == "fail"
    assert "artifact.txt: sha256 mismatch" in check.detail


def test_verdict_fails_when_any_check_is_not_pass(tmp_path: Path) -> None:
    # a single failing check flips the verdict even with everything else green
    data = example_contract_data()
    data["nets"].append({"id": "N4", "signal_class": "power", "voltage_v": 1.0, "current_a": 0.0})
    assert _report(data).verdict == "fail"


def test_splice_integrity_survives_undeclared_splice_endpoint() -> None:
    data = example_contract_data()
    contract = HarnessContract.model_validate(data)
    # an endpoint citing a splice the contract never declared must not
    # crash the leg counter (the connectivity gate reports it instead)
    contract.wires[0].from_endpoint.splice = "SP9"
    contract.wires[0].from_endpoint.connector = None
    contract.wires[0].from_endpoint.cavity = None
    checks = _checks(run_gates(contract), "splice_integrity")
    assert not [c for c in checks if "check error" in c.detail]


def test_ampacity_explicit_curve_not_spec_table() -> None:
    data = example_contract_data()
    # spec "AVSS" would derate to 1.0 at 60C; the declared curve says 0.4.
    wt = dict(data["wire_types"][0])
    wt["spec"] = "AVSS"
    wt["temp_derating"] = [
        {"temperature_c": 40.0, "factor": 0.5},
        {"temperature_c": 80.0, "factor": 0.3},
    ]
    data["wire_types"][0] = wt
    check = next(c for c in _checks(_report(data), "ampacity") if c.subject == "W1")
    assert check.limit == round(12.7 * 0.4 * bundle_derating(2), 4)


def test_terminal_compat_skips_endpoint_with_splice() -> None:
    contract = HarnessContract.model_validate(example_contract_data())
    # malformed endpoint carrying both a splice and a connector: the splice
    # wins and no per-endpoint terminal check is emitted
    contract.wires[0].from_endpoint.splice = "SP1"
    checks = _checks(run_gates(contract), "terminal_compatibility")
    assert not [c for c in checks if c.subject == "W1:C1:1"]


def test_terminal_gauge_at_upper_bound_still_passes() -> None:
    data = example_contract_data()
    # WT1 gauge 0.5 mm2 is exactly the cavity's upper accepts bound
    check = next(
        c for c in _checks(_report(data), "terminal_compatibility") if c.subject == "W1:C1:1"
    )
    assert check.status == "pass"


def test_route_geometry_equal_length_has_no_detail() -> None:
    data = example_contract_data()
    data["routes"][0]["anchors"] = ["A1", "A2"]
    data["imported_sources"] = [
        {
            "id": "I1",
            "system": "mech",
            "ref": "x.json",
            "anchors": ["A1", "A2"],
            "anchor_points": [
                {"name": "A1", "position_mm": [0.0, 0.0, 0.0]},
                {"name": "A2", "position_mm": [500.0, 0.0, 0.0]},
            ],
        }
    ]
    check = _checks(_report(data), "route_geometry")[0]
    assert check.status == "pass"
    assert check.detail == ""


def test_sim_pdn_default_base_dir_does_not_error() -> None:
    data = example_contract_data()
    data["simulation"] = {
        "rails": [
            {
                "net": "N1",
                "source": {"connector": "C1", "cavity": "1"},
                "load": {"connector": "C2", "cavity": "1"},
                "return_net": "N2",
                "return_source": {"connector": "C1", "cavity": "2"},
                "return_load": {"connector": "C2", "cavity": "2"},
            }
        ],
        "response_path": "out/sim.sim-response.json",
    }
    # run_gates without base_dir resolves against the workspace root; the
    # unanswered response is unknown, never a crash inside the check
    checks = _checks(_report(data), "sim_pdn")
    assert checks
    assert not [c for c in checks if "check error" in c.detail]


def test_terminal_gauge_at_lower_bound_still_passes() -> None:
    data = example_contract_data()
    _wire_type(data, "WT1")["gauge_mm2"] = 0.08  # exactly accepts_mm2[0]
    check = next(
        c for c in _checks(_report(data), "terminal_compatibility") if c.subject == "W1:C1:1"
    )
    assert check.status == "pass"

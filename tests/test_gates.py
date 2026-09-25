"""Gate tests: golden contract passes; corrupted inputs fail closed.

Negative tests deliberately corrupt the judged input and confirm the
corrupted contract fails the expected check — the gates are the sole
pass/fail authority.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from helpers import example_contract_data
from wire.contract import HarnessContract
from wire.export import export_design
from wire.gates import run_gates

requires_drawio = pytest.mark.skipif(
    shutil.which("drawio") is None or shutil.which("xvfb-run") is None,
    reason="export needs drawio-desktop + xvfb (both ship in the wire-tools image)",
)


def _verdict(
    data: dict[str, Any], out_dir: Path | None = None
) -> tuple[HarnessContract, dict[str, list[str]], str]:
    contract = HarnessContract.model_validate(data)
    report = run_gates(contract, out_dir)
    by_id: dict[str, list[str]] = {}
    for check in report.checks:
        by_id.setdefault(check.id, []).append(check.status)
    return contract, by_id, report.verdict


@requires_drawio
def test_golden_contract_passes(tmp_path: Path) -> None:
    contract, _, _ = _verdict(example_contract_data(), tmp_path)
    export_design(contract, tmp_path)
    report = run_gates(contract, tmp_path)
    by_id: dict[str, list[str]] = {}
    for check in report.checks:
        by_id.setdefault(check.id, []).append(check.status)
    assert report.verdict == "pass"
    for check_id, statuses in by_id.items():
        assert "fail" not in statuses and "unknown" not in statuses, check_id


def test_cavity_double_assignment_fails() -> None:
    data = example_contract_data()
    data["wires"][1]["to_endpoint"]["cavity"] = "1"
    _, by_id, verdict = _verdict(data)
    assert verdict == "fail"
    assert "fail" in by_id["cavity_occupancy"]


def test_uncovered_net_fails() -> None:
    data = example_contract_data()
    data["nets"].append({"id": "N9", "signal_class": "signal", "voltage_v": 5.0, "current_a": 0.1})
    _, by_id, verdict = _verdict(data)
    assert verdict == "fail"
    assert "fail" in by_id["netlist_coverage"]


def test_ampacity_fails_on_small_gauge() -> None:
    data = example_contract_data()
    data["nets"][0]["current_a"] = 30.0
    _, by_id, verdict = _verdict(data)
    assert verdict == "fail"
    assert "fail" in by_id["ampacity"]


def test_voltage_drop_fails_on_long_wire() -> None:
    data = example_contract_data()
    data["wires"][0]["length_m"] = 50.0
    _, by_id, verdict = _verdict(data)
    assert verdict == "fail"
    assert "fail" in by_id["voltage_drop"]


def test_insulation_fails_on_high_voltage() -> None:
    data = example_contract_data()
    data["nets"][0]["voltage_v"] = 400.0
    _, by_id, verdict = _verdict(data)
    assert verdict == "fail"
    assert "fail" in by_id["insulation_rating"]


def test_bend_radius_fails_below_limit() -> None:
    data = example_contract_data()
    data["routes"][0]["segments"][0]["min_bend_radius_mm"] = 4.0
    _, by_id, verdict = _verdict(data)
    assert verdict == "fail"
    assert "fail" in by_id["bend_radius"]


def test_bend_radius_unknown_without_declaration() -> None:
    data = example_contract_data()
    data["routes"][0]["segments"][0]["min_bend_radius_mm"] = None
    _, by_id, verdict = _verdict(data)
    assert verdict == "fail"
    assert "unknown" in by_id["bend_radius"]


def test_unrouted_wire_fails_closed() -> None:
    data = example_contract_data()
    data["wires"][2]["route"] = None
    _, by_id, verdict = _verdict(data)
    assert verdict == "fail"
    assert "unknown" in by_id["bend_radius"]


def test_segregation_violation_fails() -> None:
    data = example_contract_data()
    data["wires"][2]["route"] = "RT1"
    _, by_id, verdict = _verdict(data)
    assert verdict == "fail"
    assert "fail" in by_id["segregation"]


def test_terminal_gauge_out_of_range_fails() -> None:
    data = example_contract_data()
    data["connectors"][0]["cavities"][0]["accepts_mm2"] = [0.6, 1.0]
    _, by_id, verdict = _verdict(data)
    assert verdict == "fail"
    assert "fail" in by_id["terminal_compatibility"]


def test_connector_rating_fails_on_current() -> None:
    data = example_contract_data()
    data["nets"][0]["current_a"] = 5.0
    _, by_id, verdict = _verdict(data)
    assert verdict == "fail"
    assert "fail" in by_id["connector_rating"]


def test_identical_housings_need_distinct_keying() -> None:
    data = example_contract_data()
    data["connectors"][1]["keying"] = "A"
    _, _, verdict = _verdict(data)
    assert verdict == "fail"


def test_mating_cycles_exceeded_fails() -> None:
    data = example_contract_data()
    data["service"]["mating_cycles"] = 500
    _, by_id, verdict = _verdict(data)
    assert verdict == "fail"
    assert "fail" in by_id["connector_rating"]


def test_anchor_without_envelope_is_unknown() -> None:
    data = example_contract_data()
    data["routes"][0]["anchors"] = ["clip-1"]
    _, by_id, verdict = _verdict(data)
    assert verdict == "fail"
    assert "unknown" in by_id["anchor_resolution"]


def test_shield_required_fails_on_unshielded() -> None:
    data = example_contract_data()
    data["nets"][2]["shield_required"] = True
    _, by_id, verdict = _verdict(data)
    assert verdict == "fail"
    assert "fail" in by_id["shielding_pairing"]


def test_manifest_unknown_without_export() -> None:
    _, by_id, _ = _verdict(example_contract_data())
    assert "unknown" in by_id["manifest_integrity"]


@pytest.mark.xdist_group("example_out")
@requires_drawio
def test_manifest_passes_after_export(tmp_path: Path) -> None:
    contract = HarnessContract.model_validate(example_contract_data())
    export_design(contract, tmp_path)
    report = run_gates(contract, tmp_path)
    by_id = {c.id: c.status for c in report.checks}
    assert by_id["manifest_integrity"] == "pass"
    assert report.verdict == "pass"


def test_splice_single_leg_fails() -> None:
    data = example_contract_data()
    data["splices"] = [{"id": "SP1"}]
    data["wires"][0]["to_endpoint"] = {"splice": "SP1"}
    _, by_id, verdict = _verdict(data)
    assert verdict == "fail"
    assert "fail" in by_id["splice_integrity"]


def test_splice_across_nets_fails() -> None:
    data = example_contract_data()
    data["splices"] = [{"id": "SP1"}]
    data["wires"][0]["to_endpoint"] = {"splice": "SP1"}
    data["wires"][1]["to_endpoint"] = {"splice": "SP1"}
    _, by_id, verdict = _verdict(data)
    assert verdict == "fail"
    assert "fail" in by_id["splice_integrity"]


def test_splice_passes_with_two_legs_one_net() -> None:
    data = example_contract_data()
    data["splices"] = [{"id": "SP1"}]
    data["wires"][0]["to_endpoint"] = {"splice": "SP1"}
    leg = dict(data["wires"][0])
    leg["id"] = "W9"
    leg["from_endpoint"] = {"splice": "SP1"}
    leg["to_endpoint"] = {"connector": "C2", "cavity": "2"}
    data["wires"].append(leg)
    _, by_id, _ = _verdict(data, None)
    assert "fail" not in by_id["splice_integrity"]


def test_housing_compatibility_mate_without_housing_fails() -> None:
    data = example_contract_data()
    data["connectors"][0]["mate"] = "2.54mm pin header"
    data["connectors"][0]["housing"] = None
    _, by_id, verdict = _verdict(data)
    assert verdict == "fail"
    assert "fail" in by_id["housing_compatibility"]


def test_housing_compatibility_duplicate_mate_fails() -> None:
    data = example_contract_data()
    data["connectors"][0]["mate"] = data["connectors"][0]["housing"]
    _, by_id, verdict = _verdict(data)
    assert verdict == "fail"
    assert "fail" in by_id["housing_compatibility"]


def test_housing_compatibility_mate_and_housing_passes() -> None:
    data = example_contract_data()
    data["connectors"][0]["mate"] = "2.54mm pin header"
    data["connectors"][0]["housing"] = "22-01-3067"
    _, by_id, _ = _verdict(data)
    assert "fail" not in by_id["housing_compatibility"]
    assert by_id["housing_compatibility"] == ["pass", "pass"]


def test_housing_compatibility_unknown_without_housing_or_mate() -> None:
    data = example_contract_data()
    data["connectors"][0]["housing"] = None
    _, by_id, verdict = _verdict(data)
    assert verdict == "fail"
    assert "unknown" in by_id["housing_compatibility"]

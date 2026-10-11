"""Formboard export and the route_fit gate."""

from __future__ import annotations

import json
from pathlib import Path

from helpers import example_contract_data
from wire import cli
from wire.contract import HarnessContract, contract_sha256
from wire.formboard import formboard, write_formboard
from wire.gates import run_gates


def _contract(**wire_lengths: float) -> HarnessContract:
    data = example_contract_data()
    for wire in data["wires"]:
        if wire["id"] in wire_lengths:
            wire["length_m"] = wire_lengths[wire["id"]]
    return HarnessContract.model_validate(data)


def _route_fit(contract: HarnessContract) -> dict[str, str]:
    return {c.subject: c.status for c in run_gates(contract).checks if c.id == "route_fit"}


def _routed(contract: HarnessContract) -> tuple[str, str, float]:
    wire = next(w for w in contract.wires if w.route is not None)
    route = next(r for r in contract.routes if r.id == wire.route)
    assert wire.route is not None
    return wire.id, wire.route, sum(s.length_m for s in route.segments)


def test_example_wires_fit_their_routes() -> None:
    contract = _contract()
    statuses = _route_fit(contract)
    assert statuses and set(statuses.values()) == {"pass"}
    board = formboard(contract)
    assert board["verdict"] == "pass" and board["contract_sha256"] == contract_sha256(contract)


def test_exact_route_length_passes_and_shorter_fails() -> None:
    wire, _, length = _routed(_contract())
    assert _route_fit(_contract(**{wire: length}))[wire] == "pass"
    short = _contract(**{wire: length - 0.001})
    assert _route_fit(short)[wire] == "fail"
    board = formboard(short)
    assert board["verdict"] == "fail" and board["short"] == [wire]


def test_stations_accumulate_segment_lengths() -> None:
    contract = _contract()
    _, route_id, length = _routed(contract)
    route = next(r for r in formboard(contract)["routes"] if r["id"] == route_id)
    assert route["segments"][0]["start_mm"] == 0.0
    assert route["segments"][-1]["end_mm"] == route["length_mm"] == round(length * 1000, 3)
    for first, second in zip(route["segments"], route["segments"][1:], strict=False):
        assert first["end_mm"] == second["start_mm"]


def test_no_routes_is_unknown(tmp_path: Path) -> None:
    data = example_contract_data()
    data["routes"] = []
    for wire in data["wires"]:
        wire["route"] = None
    result = write_formboard(HarnessContract.model_validate(data), tmp_path)
    assert result["verdict"] == "fail" and result["unknown"] == ["routes"]


def test_cli_writes_artifact(tmp_path: Path) -> None:
    contract_path = tmp_path / "h.contract.json"
    contract_path.write_text(_contract().model_dump_json(), encoding="utf-8")
    assert cli.main(["formboard", "--contract", str(contract_path)]) == 0
    artifact = json.loads((tmp_path / "WH-0001.wire-formboard.json").read_text(encoding="utf-8"))
    assert artifact["artifact_kind"] == "wire_formboard"

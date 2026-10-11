"""Continuity test table export for production-engineering."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from helpers import example_contract_data
from wire import cli
from wire.continuity import continuity_table, write_continuity_table
from wire.contract import HarnessContract, contract_sha256


def _contract(**changes: Any) -> HarnessContract:
    return HarnessContract.model_validate(example_contract_data() | changes)


def test_every_wire_end_lands_in_one_group_per_net() -> None:
    contract = _contract()
    table = continuity_table(contract)
    assert table["verdict"] == "pass", table["unknown"]
    assert table["contract_sha256"] == contract_sha256(contract)
    points = [point for group in table["groups"] for point in group["points"]]
    assert len(points) == len(set(points))
    expected = {
        f"{end.connector}:{end.cavity}"
        for wire in contract.wires
        for end in (wire.from_endpoint, wire.to_endpoint)
        if end.connector is not None
    }
    assert set(points) == expected
    assert all(len(group["nets"]) == 1 for group in table["groups"])


def test_splice_joins_its_legs_into_one_group() -> None:
    data = example_contract_data()
    first = data["wires"][0]
    data["splices"] = [*data.get("splices", []), {"id": "SP9"}]
    leg_a = first | {"id": "W90", "to_endpoint": {"splice": "SP9"}}
    leg_b = first | {"id": "W91", "from_endpoint": {"splice": "SP9"}}
    data["wires"] = [leg_a, leg_b, *data["wires"][1:]]
    table = continuity_table(HarnessContract.model_validate(data))
    group = next(g for g in table["groups"] if "W90" in g["wires"])
    assert group["wires"] == ["W90", "W91"]
    assert len(group["points"]) == 2
    assert table["verdict"] == "pass", table["unknown"]


def test_conductor_carrying_two_nets_fails() -> None:
    data = example_contract_data()
    first = data["wires"][0]
    other = next(w for w in data["wires"] if w["net"] != first["net"])
    data["wires"].append(
        first | {"id": "W99", "net": other["net"], "to_endpoint": other["to_endpoint"]}
    )
    table = continuity_table(HarnessContract.model_validate(data))
    assert table["verdict"] == "fail"
    assert any("several nets" in item for item in table["unknown"])


def test_dead_end_splice_leg_fails() -> None:
    data = example_contract_data()
    data["splices"] = [*data.get("splices", []), {"id": "SP9"}]
    data["wires"][0] = data["wires"][0] | {"to_endpoint": {"splice": "SP9"}}
    table = continuity_table(HarnessContract.model_validate(data))
    assert table["verdict"] == "fail"
    assert any("fewer than two" in item for item in table["unknown"])


def test_cli_writes_the_table(tmp_path: Path) -> None:
    contract_path = tmp_path / "harness.wire.json"
    contract_path.write_text(json.dumps(example_contract_data()), encoding="utf-8")
    out = tmp_path / "out"
    result = cli.cmd_continuity(cli.argparse.Namespace(contract=str(contract_path), out=str(out)))
    assert result["verdict"] == "pass"
    written = json.loads(Path(result["path"]).read_text(encoding="utf-8"))
    assert written == continuity_table(_contract())
    assert write_continuity_table(_contract(), out)["path"] == result["path"]

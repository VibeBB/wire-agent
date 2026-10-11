"""Crimp-condition table: coverage gate and the production-engineering export."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from helpers import example_contract_data
from wire import cli
from wire.contract import HarnessContract, contract_sha256
from wire.crimp import crimp_table, write_crimp_table
from wire.gates import run_gates

TERMINAL = "SXH-001T-P0.6"


def _cc(cid: str, gauge: float, **changes: Any) -> dict[str, Any]:
    return {
        "id": cid,
        "terminal": TERMINAL,
        "gauge_mm2": gauge,
        "crimp_height_mm": 0.9,
        "crimp_height_tol_mm": 0.03,
        "pull_force_min_n": 30.0,
        "applicator": "AP-SXH-01",
        "source": "terminal application specification rev C",
        **changes,
    }


def _contract(conditions: list[dict[str, Any]] | None = None) -> HarnessContract:
    data = example_contract_data()
    data["crimp_conditions"] = (
        [_cc("CC1", 0.5), _cc("CC2", 0.35)] if conditions is None else conditions
    )
    return HarnessContract.model_validate(data)


def _crimp_checks(contract: HarnessContract) -> dict[str, Any]:
    return {c.subject: c for c in run_gates(contract).checks if c.id == "crimp_conditions"}


def test_every_termination_has_a_condition() -> None:
    checks = _crimp_checks(_contract())
    assert set(checks) == {f"W{n}:{end}" for n in (1, 2, 3) for end in "ab"}
    assert all(c.status == "pass" for c in checks.values())
    assert checks["W3:a"].detail == "CC2 (AP-SXH-01)"


def test_missing_gauge_fails() -> None:
    checks = _crimp_checks(_contract([_cc("CC1", 0.5)]))
    assert checks["W3:a"].status == "fail"
    assert checks["W3:a"].detail == f"no crimp condition for {TERMINAL} on 0.35 mm2"
    assert checks["W1:a"].status == "pass"


def test_undeclared_terminal_is_unknown() -> None:
    data = example_contract_data()
    data["wires"][0]["terminal_b"] = None
    data["crimp_conditions"] = [_cc("CC1", 0.5), _cc("CC2", 0.35)]
    checks = _crimp_checks(HarnessContract.model_validate(data))
    assert checks["W1:b"].status == "unknown"


def test_absent_table_adds_no_check_and_keeps_digest() -> None:
    plain = HarnessContract.model_validate(example_contract_data())
    assert not _crimp_checks(plain)
    assert contract_sha256(plain) != contract_sha256(_contract())
    assert contract_sha256(plain) == contract_sha256(_contract([]))


@pytest.mark.parametrize(
    "conditions",
    [
        [_cc("CC1", 0.5), _cc("CC2", 0.5)],
        [_cc("CC1", 0.5), _cc("CC1", 0.35)],
        [_cc("CC1", 0.5, crimp_height_tol_mm=0.9)],
        [_cc("CC1", 0.5, source="")],
        [_cc("CC1", 0.5, pull_force_min_n=0)],
        [_cc("X1", 0.5)],
    ],
)
def test_invalid_tables_are_rejected(conditions: list[dict[str, Any]]) -> None:
    with pytest.raises(ValidationError):
        _contract(conditions)


def test_table_lists_ends_per_condition() -> None:
    contract = _contract()
    table = crimp_table(contract)
    assert table["verdict"] == "pass" and table["unknown"] == []
    assert table["contract_sha256"] == contract_sha256(contract)
    ends = {c["id"]: c["ends"] for c in table["conditions"]}
    assert ends == {"CC1": ["W1:a", "W1:b", "W2:a", "W2:b"], "CC2": ["W3:a", "W3:b"]}


def test_incomplete_table_fails_export(tmp_path: Path) -> None:
    result = write_crimp_table(_contract([_cc("CC1", 0.5)]), tmp_path)
    assert result["verdict"] == "fail" and result["unknown"] == ["W3:a", "W3:b"]
    empty = crimp_table(HarnessContract.model_validate(example_contract_data()))
    assert empty["verdict"] == "fail" and empty["unknown"] == ["crimp_conditions"]


def test_cli_writes_artifact(tmp_path: Path) -> None:
    contract_path = tmp_path / "h.contract.json"
    contract_path.write_text(_contract().model_dump_json(), encoding="utf-8")
    assert cli.main(["crimp", "--contract", str(contract_path)]) == 0
    artifact = json.loads((tmp_path / "WH-0001.wire-crimp.json").read_text(encoding="utf-8"))
    assert artifact["artifact_kind"] == "wire_crimp" and len(artifact["conditions"]) == 2

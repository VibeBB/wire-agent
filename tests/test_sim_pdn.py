"""wire → simulation-agent PDN handoff and its hash-bound response."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from helpers import example_contract_data
from wire import cli
from wire.contract import HarnessContract
from wire.gates import run_gates
from wire.sim_pdn import expected_request, pdn_brief, pdn_check, pdn_findings, write_sim_request

RESPONSE = "sim/WH-0001.pdn.sim-response.json"
LOOP: dict[str, Any] = {
    "net": "N1",
    "source": {"connector": "C1", "cavity": "1"},
    "load": {"connector": "C2", "cavity": "1"},
    "return_net": "N2",
    "return_source": {"connector": "C1", "cavity": "2"},
    "return_load": {"connector": "C2", "cavity": "2"},
}
PASSING: list[dict[str, Any]] = [
    {"id": "pdn.N1.drop.N1/C2.1", "verdict": "pass", "measured": 0.0757, "limit": "≤ 0.72 V"},
]


def _contract(rail: dict[str, Any] | None = None, **changes: Any) -> HarnessContract:
    data = example_contract_data()
    link: dict[str, Any] = {"rails": [rail or LOOP], "response_path": RESPONSE, **changes}
    return HarnessContract.model_validate({**data, "simulation": link})


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _answer(
    root: Path,
    contract: HarnessContract,
    checks: list[dict[str, Any]],
    *,
    status: str | None = None,
    report_verdict: str | None = None,
) -> Path:
    """Play simulation-agent: write request (wire), report and response (sim)."""
    out = write_sim_request(contract, root / "sim", root=root)
    rows: list[dict[str, Any]] = [{"analysis": "pdn", "detail": "", **c} for c in checks]
    statuses = {c["verdict"] for c in rows}
    verdict = "fail" if "fail" in statuses else "unknown" if "unknown" in statuses else "pass"
    report = root / "out" / "WH-0001-pdn" / "sim-report.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps({"schema_version": 1, "verdict": report_verdict or verdict, "checks": rows}),
        encoding="utf-8",
    )
    status = status or {"pass": "accepted", "fail": "rejected"}.get(verdict, "needs_info")
    response: dict[str, Any] = {
        "schema_version": 2,
        "request_id": out["request_id"],
        "request_sha256": _sha(Path(out["request"])),
        "brief_sha256": out["sim_brief_sha256"],
        "status": status,
        "verdict": verdict if status in ("accepted", "rejected") else None,
        "reasons": [] if status in ("accepted", "rejected") else ["no load current"],
    }
    if status in ("accepted", "rejected"):
        response["report_path"] = "out/WH-0001-pdn/sim-report.json"
        response["sha256"] = _sha(report)
    path = root / RESPONSE
    path.write_text(json.dumps(response), encoding="utf-8")
    return path


def _statuses(contract: HarnessContract, root: Path, response: Path | None) -> list[str]:
    return [status for _, status, _, _ in pdn_findings(contract, response, root)]


def test_brief_builds_one_loop_with_return_path_at_ambient() -> None:
    rail = pdn_brief(_contract())["pdn"]["rails"][0]
    assert rail["source_v"] == 24.0
    assert rail["max_drop_v"] == pytest.approx(24.0 * 0.03)
    assert rail["temperature_c"] == 60.0
    assert rail["source_node"] == "N1/C1.1"
    assert rail["return_source_node"] == "N2/C1.2"
    assert rail["loads"] == [{"node": "N1/C2.1", "current_a": 2.0, "return_node": "N2/C2.2"}]
    assert [b["ref"] for b in rail["branches"]] == ["W1", "W2"]
    assert all("ampacity_a" not in b for b in rail["branches"])
    assert rail["branches"][0]["resistance_ohm_per_km"] == 32.7


def test_explicit_net_limit_wins_over_default_fraction() -> None:
    data = example_contract_data()
    data["nets"][0]["max_voltage_drop_v"] = 0.2
    contract = HarnessContract.model_validate({**data, "simulation": {"rails": [LOOP]}})
    assert pdn_brief(contract)["pdn"]["rails"][0]["max_drop_v"] == 0.2


def test_request_is_wire_pdn_and_id_ignores_response_path(tmp_path: Path) -> None:
    out = write_sim_request(_contract(), tmp_path / "sim", root=tmp_path)
    request = json.loads(Path(out["request"]).read_text(encoding="utf-8"))
    assert (request["from_system"], request["kind"]) == ("wire", "pdn")
    assert request["brief_path"] == "sim/WH-0001.pdn.sim.json"
    assert request["request_id"] == f"WH-0001-pdn-{out['sim_brief_sha256'][:12]}"
    moved = _contract(response_path="elsewhere/x.sim-response.json")
    assert expected_request(moved) == expected_request(_contract())


def test_pass_round_trip_reports_simulation_checks(tmp_path: Path) -> None:
    contract = _contract()
    response = _answer(tmp_path, contract, PASSING)
    result = pdn_check(contract, response, tmp_path)
    assert result["verdict"] == "pass"
    assert result["checks"][1]["subject"] == "N1.drop.N1/C2.1"
    assert result["checks"][1]["measured"] == 0.0757


def test_fail_stays_fail_and_carries_guidance(tmp_path: Path) -> None:
    contract = _contract()
    failing = [{**PASSING[0], "verdict": "fail", "margin": -0.1, "guidance": ["use WT2"]}]
    response = _answer(tmp_path, contract, failing)
    result = pdn_check(contract, response, tmp_path)
    assert result["verdict"] == "fail"
    assert "margin -0.1" in result["checks"][1]["detail"]
    assert "fix: use WT2" in result["checks"][1]["detail"]


def test_stale_contract_fails(tmp_path: Path) -> None:
    response = _answer(tmp_path, _contract(), PASSING)
    data = example_contract_data()
    data["wires"][0]["length_m"] = 5.0
    longer = HarnessContract.model_validate(
        {**data, "simulation": {"rails": [LOOP], "response_path": RESPONSE}}
    )
    assert _statuses(longer, tmp_path, response) == ["fail"]


def test_tampered_request_and_report_fail(tmp_path: Path) -> None:
    contract = _contract()
    response = _answer(tmp_path, contract, PASSING)
    report = tmp_path / "out" / "WH-0001-pdn" / "sim-report.json"
    report.write_text(report.read_text(encoding="utf-8") + " ", encoding="utf-8")
    assert _statuses(contract, tmp_path, response) == ["fail"]
    response = _answer(tmp_path, contract, PASSING)
    request = tmp_path / "sim" / "WH-0001.pdn.sim-request.json"
    request.write_text(request.read_text(encoding="utf-8") + " ", encoding="utf-8")
    assert _statuses(contract, tmp_path, response) == ["fail"]


@pytest.mark.parametrize("status", ["needs_info", "deferred"])
def test_unanswered_is_unknown(tmp_path: Path, status: str) -> None:
    contract = _contract()
    response = _answer(tmp_path, contract, PASSING, status=status)
    assert _statuses(contract, tmp_path, response) == ["unknown"]


def test_missing_unset_or_malformed_response_is_unknown(tmp_path: Path) -> None:
    contract = _contract()
    assert _statuses(contract, tmp_path, None) == ["unknown"]
    assert _statuses(contract, tmp_path, tmp_path / RESPONSE) == ["unknown"]
    response = _answer(tmp_path, contract, PASSING)
    response.write_text('{"schema_version": 2}', encoding="utf-8")
    assert _statuses(contract, tmp_path, response) == ["unknown"]


def test_report_without_pdn_checks_or_verdict_mismatch(tmp_path: Path) -> None:
    contract = _contract()
    other = [{"id": "thermal.U1.tj", "verdict": "pass", "measured": 50.0}]
    assert _statuses(contract, tmp_path, _answer(tmp_path, contract, other)) == ["unknown"]
    mismatch = _answer(tmp_path, contract, PASSING, report_verdict="fail")
    assert _statuses(contract, tmp_path, mismatch) == ["fail"]


def test_gate_is_unknown_until_answered_and_absent_without_section(tmp_path: Path) -> None:
    plain = HarnessContract.model_validate(example_contract_data())
    assert not [c for c in run_gates(plain).checks if c.id == "sim_pdn"]
    pending = [c for c in run_gates(_contract(), base_dir=tmp_path).checks if c.id == "sim_pdn"]
    assert [c.status for c in pending] == ["unknown"]


@pytest.mark.parametrize(
    "rail",
    [
        {**LOOP, "net": "N9"},
        {**LOOP, "return_net": "N1"},
        {**LOOP, "load": LOOP["source"]},
        {**LOOP, "load": {"connector": "C2", "cavity": "2"}},
        {key: value for key, value in LOOP.items() if key != "return_load"},
        {**LOOP, "net": "N2", "return_net": None, "return_source": None, "return_load": None},
    ],
)
def test_invalid_rails_are_rejected(rail: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _contract(rail)


def test_duplicate_rail_is_rejected() -> None:
    data = example_contract_data()
    with pytest.raises(ValidationError):
        HarnessContract.model_validate({**data, "simulation": {"rails": [LOOP, LOOP]}})


def test_cli_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("OPENHANDS_PROJECT_DIR", str(tmp_path))
    contract = _contract()
    path = tmp_path / "harness.contract.json"
    path.write_text(contract.model_dump_json(), encoding="utf-8")
    assert cli.main(["sim-request", "--contract", str(path), "--out", str(tmp_path / "sim")]) == 0
    capsys.readouterr()
    assert cli.main(["sim-check", "--contract", str(path)]) != 0
    assert json.loads(capsys.readouterr().out)["verdict"] == "unknown"
    _answer(tmp_path, contract, PASSING)
    assert cli.main(["sim-check", "--contract", str(path)]) == 0

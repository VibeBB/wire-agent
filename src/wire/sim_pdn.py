"""Supply-loop handoff to simulation-agent (PDN) and its hash-bound answer."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .contract import Endpoint, HarnessContract, HarnessWire
from .standards import DEFAULT_VOLTAGE_DROP_FRACTION
from .workspace import workspace_path

CheckStatus = Literal["pass", "fail", "unknown"]
Finding = tuple[str, CheckStatus, float | None, str]

KIND = "pdn"
_REQUEST_SUFFIX = ".sim-request.json"
_RESPONSE_SUFFIX = ".sim-response.json"


class SimResponse(BaseModel):
    """Mirror of simulation-agent's ``SimulationResponse`` (schema v2)."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    schema_version: Literal[2]
    request_id: str = Field(min_length=1)
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    brief_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    status: Literal["accepted", "rejected", "deferred", "needs_info"]
    verdict: Literal["pass", "fail", "unknown"] | None = None
    report_path: str | None = None
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    decision_refs: list[str] = Field(default_factory=list[str])
    reasons: list[str] = Field(default_factory=list[str])

    @model_validator(mode="after")
    def validate_verdict(self) -> SimResponse:
        if self.status == "accepted" and self.verdict != "pass":
            raise ValueError("accepted responses require a pass verdict")
        if self.status == "rejected" and self.verdict != "fail":
            raise ValueError("rejected responses require a fail verdict")
        if (self.report_path is None) != (self.sha256 is None):
            raise ValueError("report_path and sha256 must be provided together")
        if self.status in ("accepted", "rejected") and self.report_path is None:
            raise ValueError("accepted and rejected responses require a hashed report")
        return self


def _node(net: str, end: Endpoint) -> str:
    if end.splice is not None:
        return f"{net}/{end.splice}"
    return f"{net}/{end.connector}.{end.cavity}"


def _branch(contract: HarnessContract, wire: HarnessWire) -> dict[str, Any]:
    wire_type = contract.wire_type_map()[wire.wire_type]
    return {
        "ref": wire.id,
        "from_node": _node(wire.net, wire.from_endpoint),
        "to_node": _node(wire.net, wire.to_endpoint),
        "kind": "wire",
        "length_m": wire.length_m,
        "resistance_ohm_per_km": wire_type.resistance_ohm_per_km,
    }


def pdn_brief(contract: HarnessContract) -> dict[str, Any]:
    """simulation-agent ``*.sim.json`` payload: one PDN rail per declared supply loop.

    Wire lengths and resistances come from the contract; simulation solves the
    series/splice network and the return path at the contract ambient with its
    copper temperature coefficient. Ampacity stays with wire's own gate.
    """
    link = contract.simulation
    if link is None:
        raise ValueError("harness contract has no simulation section")
    nets = contract.net_map()
    rails: list[dict[str, Any]] = []
    for rail in link.rails:
        net = nets[rail.net]
        limit = (
            net.max_voltage_drop_v
            if net.max_voltage_drop_v is not None
            else net.voltage_v * DEFAULT_VOLTAGE_DROP_FRACTION
        )
        loop_nets = [rail.net] if rail.return_net is None else [rail.net, rail.return_net]
        branches = [_branch(contract, wire) for wire in contract.wires if wire.net in loop_nets]
        nodes = sorted({b[key] for b in branches for key in ("from_node", "to_node")})
        load: dict[str, Any] = {"node": _node(rail.net, rail.load), "current_a": net.current_a}
        payload: dict[str, Any] = {
            "name": rail.net,
            "source_v": net.voltage_v,
            "max_drop_v": limit,
            "temperature_c": contract.ambient_temperature_c,
            "source_node": _node(rail.net, rail.source),
            "nodes": nodes,
            "branches": branches,
            "loads": [load],
        }
        if rail.return_net is not None:
            assert rail.return_source is not None and rail.return_load is not None
            payload["return_source_node"] = _node(rail.return_net, rail.return_source)
            load["return_node"] = _node(rail.return_net, rail.return_load)
        rails.append(payload)
    return {
        "schema_version": 1,
        "name": contract.contract_id,
        "description": f"wire PDN handoff ({contract.contract_id} rev {contract.revision})",
        "pdn": {"rails": rails},
    }


def _brief_text(contract: HarnessContract) -> str:
    return json.dumps(pdn_brief(contract), indent=2, sort_keys=True) + "\n"


def expected_request(contract: HarnessContract) -> tuple[str, str]:
    """``(request_id, sim brief sha256)`` the current contract would request."""
    digest = hashlib.sha256(_brief_text(contract).encode("utf-8")).hexdigest()
    return f"{contract.contract_id}-{KIND}-{digest[:12]}", digest


def write_sim_request(
    contract: HarnessContract, out_dir: Path, *, root: Path | None = None
) -> dict[str, Any]:
    """Write the sim brief and its v1 ``*.sim-request.json``; ``root`` relativises paths."""
    text = _brief_text(contract)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{contract.contract_id}.{KIND}"
    sim_path = out_dir / f"{stem}.sim.json"
    sim_path.write_text(text, encoding="utf-8")
    request_id, digest = expected_request(contract)
    brief_ref = (sim_path.relative_to(root) if root is not None else sim_path).as_posix()
    assert contract.simulation is not None
    rails = [rail.net for rail in contract.simulation.rails]
    request = {
        "schema_version": 1,
        "from_system": "wire",
        "request_id": request_id,
        "kind": KIND,
        "brief_path": brief_ref,
        "question": (
            f"Solve the supply loops {', '.join(rails)} of {contract.contract_id} "
            "(series wires, splices and return path at ambient) and answer with a sim-response."
        ),
        "requested_by": "wire",
    }
    request_path = out_dir / f"{stem}{_REQUEST_SUFFIX}"
    request_path.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "verdict": "pass",
        "contract_id": contract.contract_id,
        "rails": rails,
        "sim_brief": brief_ref,
        "sim_brief_sha256": digest,
        "request": str(request_path),
        "request_id": request_id,
    }


def resolve_response(contract: HarnessContract, base_dir: Path) -> Path | None:
    """Path of ``simulation.response_path`` relative to ``base_dir`` (or ``None``)."""
    if contract.simulation is None or contract.simulation.response_path is None:
        return None
    candidate = Path(contract.simulation.response_path)
    return candidate if candidate.is_absolute() else base_dir / candidate


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> Any:
    if path.is_symlink():
        raise ValueError(f"{path.name} is a symlink")
    return json.loads(path.read_text(encoding="utf-8"))


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if math.isfinite(value) else None


def _report_findings(report: Any, response: SimResponse) -> list[Finding]:
    prefix = f"{KIND}."
    if not isinstance(report, dict):
        return [("report", "unknown", None, "sim report is not a JSON object")]
    data: dict[str, Any] = report  # pyright: ignore[reportUnknownVariableType]
    raw_checks: Any = data.get("checks")
    if not isinstance(raw_checks, list):
        return [("report", "unknown", None, "sim report has no checks list")]
    findings: list[Finding] = []
    for raw in raw_checks:  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(raw, dict):
            return [("report", "unknown", None, "sim report check is not an object")]
        item: dict[str, Any] = raw  # pyright: ignore[reportUnknownVariableType]
        check_id, verdict = item.get("id"), item.get("verdict")
        if not isinstance(check_id, str) or not check_id.startswith(prefix):
            continue
        if verdict not in ("pass", "fail", "unknown"):
            return [("report", "unknown", None, f"{check_id} has no pass/fail/unknown verdict")]
        detail = str(item.get("detail") or "")
        limit = item.get("limit")
        if limit is not None:
            detail = f"{detail}; limit {limit}" if detail else f"limit {limit}"
        margin = _number(item.get("margin"))
        if margin is not None:
            detail = f"{detail}; margin {margin:.6g}"
        guidance: object = item.get("guidance")
        if isinstance(guidance, list):
            fixes = [str(line) for line in guidance if isinstance(line, str)]  # pyright: ignore[reportUnknownVariableType]
            if fixes:
                detail = f"{detail}; fix: {' | '.join(fixes)}"
        findings.append(
            (check_id.removeprefix(prefix), verdict, _number(item.get("measured")), detail)
        )
    if not findings:
        return [("report", "unknown", None, f"sim report has no {KIND} checks")]
    if data.get("verdict") != response.verdict:
        return [
            (
                "report",
                "fail",
                None,
                f"report verdict {data.get('verdict')!r} != response verdict {response.verdict!r}",
            )
        ]
    return findings


def pdn_findings(
    contract: HarnessContract, response_path: Path | None, root: Path
) -> list[Finding]:
    """``(subject, status, measured, detail)`` per simulation PDN result; fail-closed.

    The response must answer the request the *current* contract would emit
    (request id and sim brief sha256), the request file beside it must match
    ``request_sha256``, and the hashed report must be unchanged. Only
    simulation's own check verdicts are reported; wire adds no judgement.
    """
    if contract.simulation is None:
        return []
    if response_path is None:
        return [("response", "unknown", None, "simulation.response_path is not set")]
    if not response_path.name.endswith(_RESPONSE_SUFFIX):
        return [("response", "unknown", None, f"not a {_RESPONSE_SUFFIX}: {response_path.name}")]
    if not response_path.is_file():
        return [("response", "unknown", None, f"simulation response missing: {response_path}")]
    try:
        response = SimResponse.model_validate(_load_json(response_path))
    except (OSError, ValueError, ValidationError) as exc:
        return [("response", "unknown", None, f"invalid simulation response: {exc}")]
    request_path = response_path.with_name(
        response_path.name.removesuffix(_RESPONSE_SUFFIX) + _REQUEST_SUFFIX
    )
    if not request_path.is_file() or request_path.is_symlink():
        return [("response", "unknown", None, f"request missing beside response: {request_path}")]
    if _sha256(request_path) != response.request_sha256:
        return [("response", "fail", None, "stale: request file changed after the response")]
    try:
        request = _load_json(request_path)
    except (OSError, ValueError) as exc:
        return [("response", "unknown", None, f"invalid request: {exc}")]
    expected_id, expected_sha = expected_request(contract)
    if not isinstance(request, dict) or (
        request.get("from_system"),  # pyright: ignore[reportUnknownMemberType]
        request.get("kind"),  # pyright: ignore[reportUnknownMemberType]
        request.get("request_id"),  # pyright: ignore[reportUnknownMemberType]
    ) != ("wire", KIND, response.request_id):
        return [("response", "fail", None, f"response does not answer a wire {KIND} request")]
    if response.request_id != expected_id or response.brief_sha256 != expected_sha:
        return [
            (
                "response",
                "fail",
                None,
                f"stale: answers {response.request_id}, current contract requests {expected_id}",
            )
        ]
    if response.status in ("needs_info", "deferred"):
        reasons = "; ".join(response.reasons) or "no reason given"
        return [("response", "unknown", None, f"simulation {response.status}: {reasons}")]
    assert response.report_path is not None and response.sha256 is not None
    try:
        report_path = workspace_path(response.report_path, root=root)
    except ValueError as exc:
        return [("report", "unknown", None, str(exc))]
    if not report_path.is_file():
        return [("report", "unknown", None, f"hashed sim report missing: {response.report_path}")]
    if _sha256(report_path) != response.sha256:
        return [("report", "fail", None, "stale: sim report changed after the response")]
    try:
        report = _load_json(report_path)
    except (OSError, ValueError) as exc:
        return [("report", "unknown", None, f"invalid sim report: {exc}")]
    findings = _report_findings(report, response)
    if findings[0][0] == "report":
        return findings
    return [("response", "pass", None, f"{response.request_id} {response.status}"), *findings]


def pdn_check(contract: HarnessContract, response_path: Path | None, root: Path) -> dict[str, Any]:
    """JSON verdict over :func:`pdn_findings`; a contract without the section is ``unknown``."""
    findings = pdn_findings(contract, response_path, root)
    if not findings:
        findings = [("simulation", "unknown", None, "harness contract has no simulation section")]
    statuses = {status for _, status, _, _ in findings}
    verdict: CheckStatus = (
        "fail" if "fail" in statuses else "unknown" if "unknown" in statuses else "pass"
    )
    return {
        "verdict": verdict,
        "contract_id": contract.contract_id,
        "checks": [
            {"subject": subject, "status": status, "measured": measured, "detail": detail}
            for subject, status, measured, detail in findings
        ],
    }


__all__ = [
    "KIND",
    "SimResponse",
    "expected_request",
    "pdn_brief",
    "pdn_check",
    "pdn_findings",
    "resolve_response",
    "write_sim_request",
]

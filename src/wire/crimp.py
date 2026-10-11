"""Crimp-condition coverage and the ``*.wire-crimp.json`` export for production-engineering."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from .contract import CrimpCondition, HarnessContract, contract_sha256

ARTIFACT_KIND = "wire_crimp"
Status = Literal["pass", "fail", "unknown"]


def _condition(contract: HarnessContract, terminal: str, gauge: float) -> CrimpCondition | None:
    return next(
        (
            c
            for c in contract.crimp_conditions
            if c.terminal == terminal and abs(c.gauge_mm2 - gauge) <= 1e-9
        ),
        None,
    )


def crimp_findings(contract: HarnessContract) -> list[tuple[str, Status, str | None, str]]:
    """``(wire end, status, condition id, detail)`` for every connector termination."""
    types = contract.wire_type_map()
    findings: list[tuple[str, Status, str | None, str]] = []
    for wire in contract.wires:
        gauge = types[wire.wire_type].gauge_mm2
        for end, endpoint, terminal in (
            ("a", wire.from_endpoint, wire.terminal_a),
            ("b", wire.to_endpoint, wire.terminal_b),
        ):
            if endpoint.connector is None:
                continue
            subject = f"{wire.id}:{end}"
            if terminal is None:
                findings.append((subject, "unknown", None, "terminal not declared"))
                continue
            condition = _condition(contract, terminal, gauge)
            if condition is None:
                findings.append(
                    (subject, "fail", None, f"no crimp condition for {terminal} on {gauge} mm2")
                )
            else:
                findings.append(
                    (subject, "pass", condition.id, f"{condition.id} ({condition.applicator})")
                )
    return findings


def crimp_table(contract: HarnessContract) -> dict[str, Any]:
    """The production-engineering handoff: conditions with the wire ends they crimp."""
    findings = crimp_findings(contract)
    ends: dict[str, list[str]] = {}
    for subject, _, condition, _ in findings:
        if condition is not None:
            ends.setdefault(condition, []).append(subject)
    unknown = (
        sorted(subject for subject, status, _, _ in findings if status != "pass")
        if contract.crimp_conditions
        else ["crimp_conditions"]
    )
    return {
        "artifact_kind": ARTIFACT_KIND,
        "schema_version": 1,
        "contract_id": contract.contract_id,
        "contract_sha256": contract_sha256(contract),
        "conditions": [
            {**c.model_dump(mode="json"), "ends": sorted(ends.get(c.id, []))}
            for c in sorted(contract.crimp_conditions, key=lambda c: c.id)
        ],
        "unknown": unknown,
        "verdict": "fail" if unknown else "pass",
    }


def write_crimp_table(contract: HarnessContract, out_dir: Path) -> dict[str, Any]:
    """Write ``<contract_id>.wire-crimp.json``; the verdict mirrors the artifact's."""
    table = crimp_table(contract)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{contract.contract_id}.wire-crimp.json"
    path.write_text(json.dumps(table, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"verdict": table["verdict"], "path": str(path), "unknown": table["unknown"]}

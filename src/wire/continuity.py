"""Continuity test table (``*.wire-continuity.json``) for production-engineering.

Every connector cavity a wire terminates in is a test point. Points joined by
wires (directly or through splices) form one continuity group: a tester must
read continuity inside a group and isolation between groups.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contract import Endpoint, HarnessContract, contract_sha256

ARTIFACT_KIND = "wire_continuity"


def _node(endpoint: Endpoint) -> str:
    if endpoint.splice is not None:
        return endpoint.splice
    return f"{endpoint.connector}:{endpoint.cavity}"


def continuity_table(contract: HarnessContract) -> dict[str, Any]:
    """Continuity groups of test points, with the nets and wires that join them."""
    parent: dict[str, str] = {}

    def find(node: str) -> str:
        while parent.setdefault(node, node) != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for wire in contract.wires:
        a, b = find(_node(wire.from_endpoint)), find(_node(wire.to_endpoint))
        parent[a] = b
    groups: dict[str, dict[str, set[str]]] = {}
    for wire in contract.wires:
        group = groups.setdefault(
            find(_node(wire.from_endpoint)), {"points": set(), "nets": set(), "wires": set()}
        )
        group["nets"].add(wire.net)
        group["wires"].add(wire.id)
        for endpoint in (wire.from_endpoint, wire.to_endpoint):
            if endpoint.splice is None:
                group["points"].add(_node(endpoint))
    unknown: list[str] = [] if contract.wires else ["wires"]
    rows: list[dict[str, Any]] = []
    for group in groups.values():
        row = {key: sorted(values) for key, values in group.items()}
        label = "+".join(row["nets"])
        if len(row["nets"]) > 1:
            unknown.append(f"{label}: one conductor carries several nets")
        if len(row["points"]) < 2:
            unknown.append(f"{label}: fewer than two connector test points")
        rows.append(row)
    rows.sort(key=lambda row: (row["nets"], row["points"]))
    return {
        "artifact_kind": ARTIFACT_KIND,
        "schema_version": 1,
        "contract_id": contract.contract_id,
        "contract_sha256": contract_sha256(contract),
        "groups": rows,
        "unknown": sorted(unknown),
        "verdict": "fail" if unknown else "pass",
    }


def write_continuity_table(contract: HarnessContract, out_dir: Path) -> dict[str, Any]:
    """Write ``<contract_id>.wire-continuity.json``; the verdict mirrors the artifact's."""
    table = continuity_table(contract)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{contract.contract_id}.wire-continuity.json"
    path.write_text(json.dumps(table, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"verdict": table["verdict"], "path": str(path), "unknown": table["unknown"]}

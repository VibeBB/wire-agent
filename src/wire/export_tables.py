from __future__ import annotations

import csv
import io
from typing import Any

from .contract import HarnessContract

__all__ = [
    "_bom",
    "_bom_csv",
    "_csv_text",
    "_cut_table_csv",
    "_wire_list_csv",
]


def _csv_text(header: list[str], rows: list[list[Any]]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue()


def _wire_list_csv(contract: HarnessContract) -> str:
    header = [
        "wire",
        "wire_type",
        "gauge_mm2",
        "color",
        "net",
        "net_ref",
        "from_connector",
        "from_cavity",
        "to_connector",
        "to_cavity",
        "route",
        "length_m",
        "strip_a_mm",
        "strip_b_mm",
        "terminal_a",
        "terminal_b",
    ]
    types = contract.wire_type_map()
    nets = contract.net_map()
    rows = [
        [
            wire.id,
            wire.wire_type,
            types[wire.wire_type].gauge_mm2,
            wire.color or "",
            wire.net,
            nets[wire.net].ref or "",
            wire.from_endpoint.connector or wire.from_endpoint.splice or "",
            wire.from_endpoint.cavity or "",
            wire.to_endpoint.connector or wire.to_endpoint.splice or "",
            wire.to_endpoint.cavity or "",
            wire.route or "",
            wire.length_m,
            wire.strip_a_mm,
            wire.strip_b_mm,
            wire.terminal_a or "",
            wire.terminal_b or "",
        ]
        for wire in sorted(contract.wires, key=lambda w: w.id)
    ]
    return _csv_text(header, rows)


def _cut_table_csv(contract: HarnessContract) -> str:
    """Cut/strip/crimp data per wire, grouped identical lengths together.

    Both ends are listed: the A and B sides may need different strip
    lengths and terminals, so wires only share a row when both sides
    match (B-side defaults to the wire-type name like A always did)."""
    header = [
        "wire_type",
        "gauge_mm2",
        "length_m",
        "strip_a_mm",
        "terminal_a",
        "strip_b_mm",
        "terminal_b",
        "wires",
        "quantity",
    ]
    types = contract.wire_type_map()
    groups: dict[tuple[Any, ...], list[str]] = {}
    for wire in contract.wires:
        wtype = types[wire.wire_type]
        key = (
            wire.wire_type,
            wtype.gauge_mm2,
            wire.length_m,
            wire.strip_a_mm,
            wire.terminal_a or wtype.name,
            wire.strip_b_mm,
            wire.terminal_b or wtype.name,
        )
        groups.setdefault(key, []).append(wire.id)
    rows = [
        [*key[:-2], key[-2], key[-1], ",".join(sorted(ids)), len(ids)]
        for key, ids in sorted(groups.items())
    ]
    return _csv_text(header, rows)


def _bom(contract: HarnessContract) -> dict[str, Any]:
    connectors = [
        {
            "connector": c.id,
            "family": c.family,
            "housing": c.housing or c.family,
            **({"mate": c.mate} if c.mate is not None else {}),
            "cavities": len(c.cavities),
            **({"keying": c.keying} if c.keying is not None else {}),
        }
        for c in sorted(contract.connectors, key=lambda c: c.id)
    ]
    housing_qty: dict[str, int] = {}
    for c in contract.connectors:
        housing_qty[c.housing or c.family] = housing_qty.get(c.housing or c.family, 0) + 1
    mate_qty: dict[str, list[str]] = {}
    for c in contract.connectors:
        if c.mate is not None:
            mate_qty.setdefault(c.mate, []).append(c.id)
    cavity_terminal: dict[tuple[str, str], str] = {}
    for c in contract.connectors:
        for cavity in c.cavities:
            if cavity.terminal:
                cavity_terminal[(c.id, cavity.id)] = cavity.terminal
    terminal_qty: dict[str, int] = {}
    for wire in contract.wires:
        for endpoint, declared in (
            (wire.from_endpoint, wire.terminal_a),
            (wire.to_endpoint, wire.terminal_b),
        ):
            name = declared
            if name is None and endpoint.connector is not None and endpoint.cavity is not None:
                name = cavity_terminal.get((endpoint.connector, endpoint.cavity))
            if name is not None:
                terminal_qty[name] = terminal_qty.get(name, 0) + 1
    wire_qty = [
        {
            "wire_type": t.id,
            "name": t.name,
            "gauge_mm2": t.gauge_mm2,
            "total_length_m": round(
                sum(w.length_m for w in contract.wires if w.wire_type == t.id), 4
            ),
        }
        for t in sorted(contract.wire_types, key=lambda t: t.id)
    ]
    return {
        "contract": contract.name,
        "revision": contract.revision,
        "connector_housings": [
            {"housing": k, "quantity": v} for k, v in sorted(housing_qty.items())
        ],
        "board_mates": [{"mate": k, "connectors": ids} for k, ids in sorted(mate_qty.items())],
        "connectors": connectors,
        "terminals": [{"terminal": k, "quantity": v} for k, v in sorted(terminal_qty.items())],
        "wire_types": wire_qty,
    }


def _bom_csv(contract: HarnessContract) -> str:
    bom = _bom(contract)
    rows: list[list[Any]] = []
    for entry in bom["connector_housings"]:
        rows.append(["connector_housing", entry["housing"], entry["quantity"], ""])
    for entry in bom["board_mates"]:
        rows.append(
            [
                "board_mate",
                entry["mate"],
                len(entry["connectors"]),
                "mates " + ",".join(entry["connectors"]),
            ]
        )
    for entry in bom["terminals"]:
        rows.append(["terminal", entry["terminal"], entry["quantity"], ""])
    for entry in bom["wire_types"]:
        rows.append(["wire_type", entry["name"], "", f"total {entry['total_length_m']} m"])
    return _csv_text(["section", "item", "quantity", "detail"], rows)

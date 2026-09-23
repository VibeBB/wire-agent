"""Deterministic artifact export.

Writes wire-list.csv, cut-table.csv, bom.json, bom.csv,
harness-diagram.svg, plus manifest.json (sha256 per file) and
provenance.json (contract hash and tool versions). Nothing here judges the
design; gates read these artifacts. Identical contract bytes produce
identical artifact bytes.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import platform
from pathlib import Path
from typing import Any

from . import __version__
from .contract import HarnessContract, contract_sha256

SVG_NS = "http://www.w3.org/2000/svg"


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
    rows = [
        [
            wire.id,
            wire.wire_type,
            types[wire.wire_type].gauge_mm2,
            wire.color or "",
            wire.net,
            wire.from_endpoint.connector,
            wire.from_endpoint.cavity,
            wire.to_endpoint.connector,
            wire.to_endpoint.cavity,
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
    """Cut/strip/crimp data per wire, grouped identical lengths together."""
    header = [
        "wire_type",
        "gauge_mm2",
        "length_m",
        "strip_mm",
        "terminal",
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
        )
        groups.setdefault(key, []).append(wire.id)
    rows = [
        [*key[:-1], key[-1], ",".join(sorted(ids)), len(ids)] for key, ids in sorted(groups.items())
    ]
    return _csv_text(header, rows)


def _bom(contract: HarnessContract) -> dict[str, Any]:
    connectors = [
        {
            "connector": c.id,
            "family": c.family,
            "housing": c.housing or c.family,
            "cavities": len(c.cavities),
        }
        for c in sorted(contract.connectors, key=lambda c: c.id)
    ]
    housing_qty: dict[str, int] = {}
    for c in contract.connectors:
        housing_qty[c.housing or c.family] = housing_qty.get(c.housing or c.family, 0) + 1
    terminal_qty: dict[str, int] = {}
    for c in contract.connectors:
        for cavity in c.cavities:
            if cavity.terminal:
                terminal_qty[cavity.terminal] = terminal_qty.get(cavity.terminal, 0) + 1
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
        "connectors": connectors,
        "terminals": [{"terminal": k, "quantity": v} for k, v in sorted(terminal_qty.items())],
        "wire_types": wire_qty,
    }


def _bom_csv(contract: HarnessContract) -> str:
    bom = _bom(contract)
    rows: list[list[Any]] = []
    for entry in bom["connector_housings"]:
        rows.append(["connector_housing", entry["housing"], entry["quantity"], ""])
    for entry in bom["terminals"]:
        rows.append(["terminal", entry["terminal"], entry["quantity"], ""])
    for entry in bom["wire_types"]:
        rows.append(["wire_type", entry["name"], "", f"total {entry['total_length_m']} m"])
    return _csv_text(["section", "item", "quantity", "detail"], rows)


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def _harness_svg(contract: HarnessContract) -> str:
    """Flat two-column schematic: connectors as boxes, wires as labeled lines."""
    connectors = sorted(contract.connectors, key=lambda c: c.id)
    left = connectors[0::2]
    right = connectors[1::2]
    rows = max(len(left), len(right), 1)
    box_w, box_h = 150.0, 26.0
    margin_y, gap_y = 40.0, 52.0
    left_x, right_x = 60.0, 560.0
    width = left_x + box_w + (right_x - left_x) + 160.0
    height = margin_y * 2 + rows * gap_y
    positions: dict[str, tuple[float, float]] = {}
    for idx, c in enumerate(left):
        positions[c.id] = (left_x, margin_y + idx * gap_y)
    for idx, c in enumerate(right):
        positions[c.id] = (right_x, margin_y + idx * gap_y)

    nets = contract.net_map()
    types = contract.wire_type_map()
    parts: list[str] = [
        f'<svg xmlns="{SVG_NS}" width="{width:.0f}" height="{height:.0f}" '
        f'viewBox="0 0 {width:.0f} {height:.0f}" font-family="monospace" font-size="11">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
    ]
    for c in connectors:
        x, y = positions[c.id]
        parts.append(
            f'<rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" rx="4" '
            f'fill="#eef2ff" stroke="#333" stroke-width="1"/>'
        )
        label = f"{c.id} {c.family} ({len(c.cavities)}p)"
        parts.append(f'<text x="{x + 8}" y="{y + 17}">{_esc(label)}</text>')
    for wire in sorted(contract.wires, key=lambda w: w.id):
        x1, y1 = positions[wire.from_endpoint.connector]
        x2, y2 = positions[wire.to_endpoint.connector]
        cy = (y1 + y2) / 2 + box_h / 2 + 4
        wtype = types[wire.wire_type]
        net = nets[wire.net]
        label = f"{wire.id} {wtype.name} {net.id}/{net.signal_class} {wire.length_m}m"
        parts.append(
            f'<path d="M {x1 + box_w} {y1 + box_h / 2} C {(x1 + x2 + box_w) / 2} {cy}, '
            f'{(x1 + x2 + box_w) / 2} {cy}, {x2} {y2 + box_h / 2}" '
            f'fill="none" stroke="#2255aa" stroke-width="1.4"/>'
        )
        parts.append(
            f'<text x="{(x1 + x2 + box_w) / 2 - 110}" y="{cy - 4}" fill="#225">{_esc(label)}</text>'
        )
    for route in contract.routes:
        parts.append(
            f"<!-- route {route.id}: {len(route.segments)} segments, "
            f"protection {route.protection} -->"
        )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def export_design(contract: HarnessContract, out_dir: Path) -> dict[str, Any]:
    """Write every projection plus manifest.json and provenance.json."""
    out_dir.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, str] = {
        "wire-list.csv": _wire_list_csv(contract),
        "cut-table.csv": _cut_table_csv(contract),
        "bom.csv": _bom_csv(contract),
        "harness-diagram.svg": _harness_svg(contract),
    }
    bom_json = json.dumps(_bom(contract), indent=2, sort_keys=True) + "\n"
    artifacts["bom.json"] = bom_json

    files: list[dict[str, Any]] = []
    for name in sorted(artifacts):
        path = out_dir / name
        path.write_text(artifacts[name], encoding="utf-8")
        files.append(
            {
                "path": name,
                "sha256": hashlib.sha256(artifacts[name].encode("utf-8")).hexdigest(),
                "bytes": len(artifacts[name].encode("utf-8")),
            }
        )

    provenance = {
        "schema_version": 1,
        "generator": f"wire-agent/{__version__}",
        "contract": contract.name,
        "contract_id": contract.contract_id,
        "revision": contract.revision,
        "contract_sha256": contract_sha256(contract),
        "imported_sources": [
            {
                "id": s.id,
                "system": s.system,
                "ref": s.ref,
                "sha256": s.sha256,
            }
            for s in contract.imported_sources
        ],
        "tool_versions": {"python": platform.python_version()},
    }
    provenance_text = json.dumps(provenance, indent=2, sort_keys=True) + "\n"
    (out_dir / "provenance.json").write_text(provenance_text, encoding="utf-8")
    files.append(
        {
            "path": "provenance.json",
            "sha256": hashlib.sha256(provenance_text.encode("utf-8")).hexdigest(),
            "bytes": len(provenance_text.encode("utf-8")),
        }
    )
    manifest = {
        "schema_version": 1,
        "contract_sha256": contract_sha256(contract),
        "files": files,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest

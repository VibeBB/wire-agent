"""Deterministic artifact export.

Writes wire-list.csv, cut-table.csv, bom.json, bom.csv, and
harness-diagram.drawio.svg (an SVG whose root `content` attribute embeds
the editable drawio model), plus manifest.json (sha256 per file) and
provenance.json (contract hash and tool versions). Nothing here judges
the design; gates read these artifacts. Identical contract bytes produce
identical artifact bytes.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import platform
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import __version__
from .contract import (
    CavitySpec,
    Endpoint,
    HarnessConnector,
    HarnessContract,
    HarnessNet,
    HarnessWire,
    WireType,
    contract_sha256,
)

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


_SIGNAL_COLORS: dict[str, str] = {
    "power": "#c00000",
    "ground": "#1a1a1a",
    "signal": "#2e7d32",
    "analog": "#1565c0",
    "data": "#6a3fb5",
    "highspeed": "#ef6c00",
    "shield": "#616161",
}

# Common wire insulation color codes (WireViz-style abbreviations). A
# HarnessWire.color of "RD/BK" means a red body with a black stripe.
_WIRE_COLORS: dict[str, str] = {
    "BK": "#1a1a1a",
    "BN": "#795548",
    "RD": "#d32f2f",
    "OG": "#f57c00",
    "YE": "#fbc02d",
    "GN": "#388e3c",
    "BU": "#1976d2",
    "VT": "#7b1fa2",
    "GY": "#757575",
    "WH": "#d0d0d0",
    "PK": "#ec407a",
    "TQ": "#26a69a",
}

_HEADER_H = 26.0
_ROW_H = 22.0
_CONN_W = 200.0
_COL_X = (60.0, 620.0)
_TOP_Y = 100.0
_GAP_Y = 48.0
_MID_CHANNEL_X = (_COL_X[0] + _CONN_W + _COL_X[1]) / 2
_SPLICE_R = 5.0


def _num(value: float) -> str:
    return f"{value:g}"


def _connector_height(connector: HarnessConnector) -> float:
    return _HEADER_H + len(connector.cavities) * _ROW_H


def _cavity_label(cavity: CavitySpec) -> str:
    details = [cavity.id]
    if cavity.terminal is not None:
        details.append(cavity.terminal)
    if cavity.accepts_mm2 is not None:
        lo, hi = cavity.accepts_mm2
        details.append(f"{_num(lo)}-{_num(hi)}mm2")
    return " · ".join(details)


def _wire_colors(code: str | None) -> list[str]:
    """Physical insulation colors for a wire; 'RD/BK' yields [base, stripe]."""
    if not code:
        return []
    colors: list[str] = []
    for part in code.split("/"):
        token = part.strip().upper()
        if token in _WIRE_COLORS:
            colors.append(_WIRE_COLORS[token])
        elif len(token) == 7 and token.startswith("#"):
            colors.append(token.lower())
    return colors


def _wire_stroke(wire: HarnessWire, net: HarnessNet) -> tuple[str, str | None]:
    """(base stroke, stripe stroke) — physical color wins, else signal class."""
    colors = _wire_colors(wire.color)
    if colors:
        return colors[0], colors[1] if len(colors) > 1 else None
    return _SIGNAL_COLORS[net.signal_class], None


def _wire_label(wire: HarnessWire, wtype: WireType, net: HarnessNet) -> str:
    color = f"{wire.color} " if wire.color else ""
    label = (
        f"{wire.id} · {color}{wtype.name} · {net.id}/{net.signal_class} · {_num(wire.length_m)}m"
    )
    if net.twisted_pair_with is not None:
        label += f" · TP\u21c4{net.twisted_pair_with}"
    return label


def _diagram_title(contract: HarnessContract) -> str:
    return f"{contract.name} · {contract.contract_id} · rev {contract.revision}"


def _diagram_geometry(
    contract: HarnessContract,
) -> tuple[dict[str, tuple[float, float]], dict[str, int], float, float]:
    """Connector origins, column assignment, and page size of the pin-table layout."""
    connectors = sorted(contract.connectors, key=lambda c: c.id)
    columns = (connectors[0::2], connectors[1::2])
    column_of = {c.id: i for i, members in enumerate(columns) for c in members}
    positions: dict[str, tuple[float, float]] = {}
    y_cursor = [_TOP_Y, _TOP_Y]
    max_y = _TOP_Y
    for column, members in enumerate(columns):
        for connector in members:
            y = y_cursor[column]
            positions[connector.id] = (_COL_X[column], y)
            y_cursor[column] = y + _connector_height(connector) + _GAP_Y
            max_y = max(max_y, y + _connector_height(connector))
    page_w = _COL_X[1] + _CONN_W + 60.0
    return positions, column_of, page_w, max_y + 60.0


def _splice_positions(
    contract: HarnessContract,
    cavity_y: dict[tuple[str, str], float],
) -> dict[str, tuple[float, float]]:
    """Each splice sits in the routing channel at the mean y of its legs."""
    legs: dict[str, list[float]] = {splice.id: [] for splice in contract.splices}
    for wire in contract.wires:
        for endpoint, other in (
            (wire.from_endpoint, wire.to_endpoint),
            (wire.to_endpoint, wire.from_endpoint),
        ):
            if endpoint.splice is not None and endpoint.splice in legs:
                key = (other.connector or "", other.cavity or "")
                legs[endpoint.splice].append(cavity_y.get(key, _TOP_Y))
    return {
        splice_id: (_MID_CHANNEL_X, sum(ys) / len(ys) if ys else _TOP_Y)
        for splice_id, ys in legs.items()
    }


def _diagram_layout(contract: HarnessContract) -> dict[str, Any]:
    """Shared geometry for the SVG body and the embedded drawio model."""
    positions, column_of, page_w, page_h = _diagram_geometry(contract)
    connectors = contract.connector_map()
    cavity_y: dict[tuple[str, str], float] = {}
    for connector in contract.connectors:
        _x, y = positions[connector.id]
        for idx, cavity in enumerate(connector.cavities):
            cavity_y[(connector.id, cavity.id)] = y + _HEADER_H + idx * _ROW_H + _ROW_H / 2
    splice_pos = _splice_positions(contract, cavity_y)
    used = {
        (endpoint.connector, endpoint.cavity)
        for wire in contract.wires
        for endpoint in (wire.from_endpoint, wire.to_endpoint)
        if endpoint.connector is not None
    }
    loop_bumps: dict[str, int] = {}
    seen_loops: dict[str, int] = {}
    for wire in sorted(contract.wires, key=lambda w: w.id):
        conn = wire.from_endpoint.connector
        if conn is not None and conn == wire.to_endpoint.connector:
            loop_bumps[wire.id] = seen_loops.get(conn, 0)
            seen_loops[conn] = seen_loops.get(conn, 0) + 1
    return {
        "positions": positions,
        "column_of": column_of,
        "page_w": page_w,
        "page_h": page_h,
        "cavity_y": cavity_y,
        "splice_pos": splice_pos,
        "used_cavities": used,
        "connectors": connectors,
        "loop_bumps": loop_bumps,
    }


def _wire_anchors(
    contract: HarnessContract,
    layout: dict[str, Any],
    wire: HarnessWire,
) -> tuple[tuple[float, float], tuple[float, float], float, bool]:
    """Attach points (x, y) for both endpoints, routing x, and loop flag."""
    positions = layout["positions"]
    column_of = layout["column_of"]
    splice_pos = layout["splice_pos"]

    def point(endpoint: Endpoint) -> tuple[float, float]:
        if endpoint.splice is not None:
            return splice_pos[endpoint.splice]
        x, _y = positions[endpoint.connector]
        mid_y = layout["cavity_y"][(endpoint.connector, endpoint.cavity)]
        col = column_of[endpoint.connector]
        x_edge = x + (_CONN_W if col == 0 else 0.0)
        return x_edge, mid_y

    loop = (
        wire.from_endpoint.connector is not None
        and wire.from_endpoint.connector == wire.to_endpoint.connector
    )
    ax, ay = point(wire.from_endpoint)
    bx, by = point(wire.to_endpoint)
    if loop:
        # Small bump on the inner edge; later loops nest further into the channel.
        seen = layout["loop_bumps"].get(wire.id, 0)
        sign = 1.0 if column_of[wire.from_endpoint.connector] == 0 else -1.0
        mid_x = ax + sign * (24.0 + seen * 12.0)
    elif ax == bx:
        mid_x = ax
    else:
        mid_x = (ax + bx) / 2
    return (ax, ay), (bx, by), mid_x, loop


def _twist_links(
    contract: HarnessContract, layout: dict[str, Any]
) -> list[tuple[tuple[float, float], tuple[float, float], str]]:
    """Dashed bands linking wire midpoints across a declared twisted pair."""
    nets = contract.net_map()
    mids: dict[str, list[tuple[float, float]]] = {}
    for wire in sorted(contract.wires, key=lambda w: w.id):
        (_ax, ay), (_bx, by), mid_x, _loop = _wire_anchors(contract, layout, wire)
        mids.setdefault(wire.net, []).append((mid_x, (ay + by) / 2))
    links: list[tuple[tuple[float, float], tuple[float, float], str]] = []
    for net in sorted(contract.nets, key=lambda n: n.id):
        peer = net.twisted_pair_with
        if peer is None or peer < net.id or peer not in nets:
            continue
        for a, b in zip(mids.get(net.id, []), mids.get(peer, []), strict=False):
            links.append((a, b, f"twisted pair {net.id}\u21c4{peer}"))
    return links


def _loop_waypoint(wire: HarnessWire, layout: dict[str, Any]) -> tuple[float, float] | None:
    """Channel-side bump point for a same-connector loop, or None."""
    if wire.from_endpoint.connector is None:
        return None
    if wire.from_endpoint.connector != wire.to_endpoint.connector:
        return None
    conn = wire.from_endpoint.connector
    positions = layout["positions"]
    column_of = layout["column_of"]
    cavity_y = layout["cavity_y"]
    col = column_of[conn]
    x_edge = positions[conn][0] + (_CONN_W if col == 0 else 0.0)
    sign = 1.0 if col == 0 else -1.0
    seen = layout["loop_bumps"].get(wire.id, 0)
    bump_x = x_edge + sign * (36.0 + seen * 18.0)
    mid_y = (
        cavity_y[(conn, wire.from_endpoint.cavity or "")]
        + cavity_y[(conn, wire.to_endpoint.cavity or "")]
    ) / 2
    return bump_x, mid_y


def _loop_points(bump: tuple[float, float] | None) -> str:
    """Waypoint Array fragment routing a loop edge through the channel."""
    if bump is None:
        return ""
    return f'<Array as="points"><mxPoint x="{_num(bump[0])}" y="{_num(bump[1])}" /></Array>'


def _endpoint_cell_id(endpoint: Endpoint) -> str:
    if endpoint.splice is not None:
        return f"splice-{endpoint.splice}"
    return f"cav-{endpoint.connector}:{endpoint.cavity}"


def _endpoint_side(endpoint: Endpoint, role: str, column_of: dict[str, int]) -> str:
    """exitX/entryX style fragment: splices hit the node perimeter, connector
    cavities pin to the inner (channel-facing) side."""
    if endpoint.splice is not None or endpoint.connector is None:
        return f"{role}X=0.5;{role}Y=0.5;{role}Dx=0;{role}Dy=0;{role}Perimeter=1;"
    side = 1 - column_of[endpoint.connector]
    return f"{role}X={side};{role}Y=0.5;{role}Dx=0;{role}Dy=0;{role}Perimeter=0;"


def _drawio_model(contract: HarnessContract, layout: dict[str, Any]) -> str:
    """mxGraphModel for the same pin-table layout; edges bind cavity cells.

    Drawio features used: container swimlanes (cavity rows move with the
    connector), a separate wires layer (toggleable/lockable), edges bound
    to cavity/splice cells, pinned exit/entry sides, dashed shielded
    strokes, and floating dashed twist-pair bands.
    """
    positions = layout["positions"]
    column_of = layout["column_of"]
    used = layout["used_cavities"]
    page_w = layout["page_w"]
    page_h = layout["page_h"]
    parts = [
        '<mxGraphModel dx="0" dy="0" grid="1" gridSize="10" guides="1" '
        'tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" '
        f'pageWidth="{_num(page_w)}" pageHeight="{_num(page_h)}" math="0" shadow="0">',
        "<root>",
        '<mxCell id="0" />',
        '<mxCell id="1" value="harness" parent="0" />',
        '<mxCell id="wires" value="wires" parent="0" />',
        f'<mxCell id="title" value="{_esc(_diagram_title(contract))}" '
        'style="text;html=1;align=left;fontSize=14;fontFamily=monospace;" vertex="1" parent="1">'
        f'<mxGeometry x="{_num(_COL_X[0])}" y="40" '
        f'width="{_num(page_w - 2 * _COL_X[0])}" height="24" as="geometry" /></mxCell>',
    ]
    for connector in sorted(contract.connectors, key=lambda c: c.id):
        x, y = positions[connector.id]
        header = f"{connector.id} · {connector.family} · {len(connector.cavities)}p"
        parts.append(
            f'<mxCell id="conn-{connector.id}" value="{_esc(header)}" '
            f'style="swimlane;startSize={_num(_HEADER_H)};html=1;whiteSpace=wrap;'
            "fillColor=#eef2ff;strokeColor=#333333;fontFamily=monospace;fontSize=11;"
            'align=left;spacingLeft=8;collapsible=0;container=1;recursiveResize=0;" '
            'vertex="1" parent="1">'
            f'<mxGeometry x="{_num(x)}" y="{_num(y)}" width="{_num(_CONN_W)}" '
            f'height="{_num(_connector_height(connector))}" as="geometry" /></mxCell>'
        )
        for idx, cavity in enumerate(connector.cavities):
            row_y = _HEADER_H + idx * _ROW_H
            free = (
                "fillColor=#f5f5f5;fontColor=#9e9e9e;"
                if (
                    connector.id,
                    cavity.id,
                )
                not in used
                else "fillColor=#ffffff;"
            )
            parts.append(
                f'<mxCell id="cav-{connector.id}:{cavity.id}" '
                f'value="{_esc(_cavity_label(cavity))}" '
                f'style="rounded=0;html=1;whiteSpace=wrap;{free}'
                "strokeColor=#bbbbbb;fontFamily=monospace;fontSize=10;align=left;"
                f'spacingLeft=6;" vertex="1" parent="conn-{connector.id}">'
                f'<mxGeometry y="{_num(row_y)}" width="{_num(_CONN_W)}" '
                f'height="{_num(_ROW_H)}" as="geometry" /></mxCell>'
            )
    for splice in sorted(contract.splices, key=lambda s: s.id):
        sx, sy = layout["splice_pos"][splice.id]
        parts.append(
            f'<mxCell id="splice-{splice.id}" value="{_esc(splice.id)} · {splice.kind}" '
            'style="ellipse;html=1;fillColor=#333333;strokeColor=none;'
            "fontFamily=monospace;fontSize=9;fontColor=#616161;"
            'verticalLabelPosition=bottom;verticalAlign=top;labelBackgroundColor=#ffffff;" '
            'vertex="1" parent="wires">'
            f'<mxGeometry x="{_num(sx - _SPLICE_R)}" y="{_num(sy - _SPLICE_R)}" '
            f'width="{_num(_SPLICE_R * 2)}" height="{_num(_SPLICE_R * 2)}" '
            'as="geometry" /></mxCell>'
        )
    nets = contract.net_map()
    types = contract.wire_type_map()
    ordered_wires = sorted(contract.wires, key=lambda w: w.id)
    # Unique vertical label offsets keep wire labels from stacking where
    # parallel edges share the routing channel.
    label_offsets = {
        wire.id: (i - (len(ordered_wires) - 1) / 2) * 14.0 for i, wire in enumerate(ordered_wires)
    }
    for wire in ordered_wires:
        net = nets[wire.net]
        wtype = types[wire.wire_type]
        color, stripe = _wire_stroke(wire, net)
        dashed = "dashed=1;" if wtype.shield != "none" else ""
        bump = _loop_waypoint(wire, layout)
        # Loop bumps sit at the connector edge; drop their labels below the
        # bump into open channel space instead of overlapping the frame.
        label_y = 30.0 if bump is not None else label_offsets[wire.id]
        parts.append(
            f'<mxCell id="wire-{wire.id}" value="{_esc(_wire_label(wire, wtype, net))}" '
            'style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;orthogonalLoop=1;'
            f"jettySize=auto;strokeWidth=1.5;strokeColor={color};{dashed}"
            "fontFamily=monospace;fontSize=10;labelBackgroundColor=#ffffff;"
            f"{_endpoint_side(wire.from_endpoint, 'exit', column_of)}"
            f'{_endpoint_side(wire.to_endpoint, "entry", column_of)}" '
            'edge="1" parent="wires" '
            f'source="{_endpoint_cell_id(wire.from_endpoint)}" '
            f'target="{_endpoint_cell_id(wire.to_endpoint)}">'
            '<mxGeometry x="0" relative="1" as="geometry">'
            f'<mxPoint y="{_num(label_y)}" as="offset" />'
            + _loop_points(bump)
            + "</mxGeometry></mxCell>"
        )
        if stripe is not None:
            parts.append(
                f'<mxCell id="wire-{wire.id}-stripe" value="" '
                'style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;orthogonalLoop=1;'
                f"jettySize=auto;strokeWidth=1;dashed=1;strokeColor={stripe};"
                f"{_endpoint_side(wire.from_endpoint, 'exit', column_of)}"
                f'{_endpoint_side(wire.to_endpoint, "entry", column_of)}" '
                'edge="1" parent="wires" '
                f'source="{_endpoint_cell_id(wire.from_endpoint)}" '
                f'target="{_endpoint_cell_id(wire.to_endpoint)}">'
                '<mxGeometry relative="1" as="geometry">'
                + _loop_points(bump)
                + "</mxGeometry></mxCell>"
            )
    for idx, (a, b, label) in enumerate(_twist_links(contract, layout)):
        parts.append(
            f'<mxCell id="twist-{idx}" value="{_esc(label)}" '
            'style="endArrow=none;html=1;rounded=0;dashed=1;strokeColor=#616161;'
            "strokeWidth=1;fontFamily=monospace;fontSize=8;fontColor=#616161;"
            'labelBackgroundColor=#ffffff;" edge="1" parent="wires">'
            '<mxGeometry relative="1" as="geometry">'
            f'<mxPoint x="{_num(a[0])}" y="{_num(a[1])}" as="sourcePoint" />'
            f'<mxPoint x="{_num(b[0])}" y="{_num(b[1])}" as="targetPoint" />'
            '<mxPoint y="-30" as="offset" />'
            "</mxGeometry></mxCell>"
        )
    parts.append("</root></mxGraphModel>")
    return "".join(parts)


def _harness_mxfile(contract: HarnessContract) -> str:
    """Drawio mxfile of the pin-table diagram.

    Every connector is a swimlane of cavity cells and every wire is an edge
    bound to its two cavity cells, so manual re-layout keeps connectivity
    attached.
    """
    layout = _diagram_layout(contract)
    model = _drawio_model(contract, layout)
    return (
        '<mxfile host="wire-agent" type="device">'
        f'<diagram id="harness" name="{_esc(contract.name)}">{model}</diagram></mxfile>'
    )


def _drawio_cli() -> list[str] | None:
    """Headless drawio-desktop export prefix, or None when unavailable."""
    if shutil.which("drawio") is None or shutil.which("xvfb-run") is None:
        return None
    return [
        "xvfb-run",
        "-a",
        "drawio",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--disable-update",
    ]


def _drawio_render(mxfile: str, fmt_args: Sequence[str]) -> bytes:
    """Render the mxfile through ``drawio -x`` and return the output bytes.

    drawio-desktop renders the canonical view (what diagrams.net shows) and
    resolves CJK glyphs through its bundled text stack — a successful run
    also proves drawio actually loads the generated model. The subprocess
    boundary keeps the Electron app out of the import set. Output bytes vary
    with the installed drawio version, so rendered artifacts are review aids
    rather than byte-stable projections.
    """
    cmd = _drawio_cli()
    if cmd is None:
        raise RuntimeError(
            "drawio export needs drawio-desktop and xvfb (both ship in the wire-tools image)"
        )
    with tempfile.TemporaryDirectory(prefix="wire-drawio-") as tmp:
        src = Path(tmp) / "harness.drawio"
        out = Path(tmp) / "out"
        src.write_text(mxfile, encoding="utf-8")
        result = subprocess.run(
            [*cmd, "-x", *fmt_args, "-o", str(out), str(src)],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0 or not out.is_file() or out.stat().st_size == 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"drawio -x {' '.join(fmt_args)} failed: {detail}")
        return out.read_bytes()


_DRAWIO_EXPORTS: dict[str, tuple[str, list[str]]] = {
    "png": ("harness-diagram.png", ["-f", "png", "-s", "2"]),
    "jpg": ("harness-diagram.jpg", ["-f", "jpg", "-s", "2", "-q", "95"]),
    "pdf": ("harness-diagram.pdf", ["-f", "pdf", "--crop"]),
    "html": ("harness-diagram.html", ["-f", "html", "-a"]),
    "svg": ("harness-diagram.svg", ["-f", "svg"]),
    "xml": ("harness-diagram.drawio", ["-f", "xml"]),
}


def drawio_export_formats() -> list[str]:
    """Formats accepted by ``--drawio`` (drawio-desktop -x outputs)."""
    return sorted(_DRAWIO_EXPORTS)


def run_drawio_export(
    input_path: Path,
    output_path: Path | None,
    fmt: str | None,
    options: Sequence[str],
) -> dict[str, Any]:
    """Proxy a drawio-desktop ``-x`` export on any supported input.

    ``options`` passes through drawio flags (pages, layers, layout, embeds,
    quality, ...) so the full CLI surface is reachable; inputs may be drawio,
    vsdx, csv, or mermaid files.
    """
    cmd = _drawio_cli()
    if cmd is None:
        raise RuntimeError(
            "drawio export needs drawio-desktop and xvfb (both ship in the wire-tools image)"
        )
    argv = [*cmd, "-x"]
    if fmt is not None:
        argv += ["-f", fmt]
    if output_path is not None:
        argv += ["-o", str(output_path)]
    argv += [*options, str(input_path)]
    result = subprocess.run(argv, capture_output=True, check=False)
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"drawio -x failed: {detail}")
    emitted = output_path or input_path.with_suffix(f".{fmt or 'pdf'}")
    return {"path": str(emitted), "exists": emitted.is_file()}


def export_design(
    contract: HarnessContract,
    out_dir: Path,
    *,
    png: bool = False,
    drawio: Sequence[str] = (),
) -> dict[str, Any]:
    """Write every projection plus manifest.json and provenance.json.

    The diagram is rendered by drawio-desktop when it is installed (canonical
    rendering, embedded model round-trips); without it the raw mxfile is
    written as ``harness-diagram.drawio`` so the design stays editable.
    ``png=True`` is a shorthand for ``drawio=["png"]`` — ``drawio`` lists
    extra formats (png, jpg, pdf, html, xml) rendered through ``drawio -x``
    for vision-capable reviewers (the OpenHands FileEditorTool auto-sends
    raster images to the LLM).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    mxfile = _harness_mxfile(contract)
    artifacts: dict[str, str] = {
        "wire-list.csv": _wire_list_csv(contract),
        "cut-table.csv": _cut_table_csv(contract),
        "bom.csv": _bom_csv(contract),
    }
    diagram_source = "drawio-desktop"
    try:
        artifacts["harness-diagram.drawio.svg"] = _drawio_render(
            mxfile, ["-f", "svg", "-e"]
        ).decode("utf-8")
    except RuntimeError:
        diagram_source = "mxfile"
        artifacts["harness-diagram.drawio"] = mxfile + "\n"
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

    extra = set(drawio)
    if png:
        extra.add("png")
    for fmt in sorted(extra):
        name, fmt_args = _DRAWIO_EXPORTS[fmt]
        rendered = _drawio_render(mxfile, fmt_args)
        path = out_dir / name
        path.write_bytes(rendered)
        files.append(
            {
                "path": name,
                "sha256": hashlib.sha256(rendered).hexdigest(),
                "bytes": len(rendered),
            }
        )

    provenance = {
        "schema_version": 1,
        "license": "BSD-3-Clause",
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
        "diagram_renderer": diagram_source,
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

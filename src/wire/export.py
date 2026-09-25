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

from . import __version__, drawio_lint
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

# Documentation strip: legend and manufacturing notes side by side below the
# pin table, inside the drawing space (bordered blocks of monospace rows).
_DOC_LEGEND_X = _COL_X[0]
_DOC_LEGEND_W = 360.0
_DOC_NOTES_X = _COL_X[0] + _DOC_LEGEND_W + 40.0
_DOC_NOTES_W = _COL_X[1] + _CONN_W - _DOC_NOTES_X
_DOC_HEADER_H = 20.0
_DOC_ROW_H = 16.0
_DOC_PAD_BOTTOM = 4.0
_DOC_GAP_TOP = 36.0


def _num(value: float) -> str:
    return f"{value:g}"


# --- Drawing sheet frame: ISO 5457 (= JIS Z 8311) + ISO 7200 title block ---
#
# Drawio page units are pixels at 100 px per inch (its A-series page formats
# are 827x1169, 1169x1654, ...), so millimetre geometry maps cleanly with
# _mm(). The frame, zone system, centring marks, and title block are drawn
# as ordinary cells on a bottom "frame" layer, which keeps the artifact
# editable in drawio and renders identically in `drawio -x` exports (the
# SVG viewBox follows the union of cell bounds — the sheet rect therefore
# defines the rendered canvas).
_PX_PER_MM = 100.0 / 25.4

# ISO 5457 A-series landscape sheets (trimmed size, mm), smallest first —
# A0 to A3 are horizontal-only; A4 may be either and we use horizontal so
# the title block sits bottom-right. JIS Z 8311 elongated sheets extend the
# short side for content past A0.
_SHEETS: tuple[tuple[str, float, float], ...] = (
    ("A4", 297.0, 210.0),
    ("A3", 420.0, 297.0),
    ("A2", 594.0, 420.0),
    ("A1", 841.0, 594.0),
    ("A0", 1189.0, 841.0),
    ("A0x2", 1189.0, 1682.0),
    ("A0x3", 1189.0, 2523.0),
)
_BORDER_LEFT_MM = 20.0  # filing margin (ISO 5457 §4.2)
_BORDER_MM = 10.0  # other three sides
_FRAME_STROKE_MM = 0.7  # drawing-space frame line
_GRID_STROKE_MM = 0.35  # grid-reference tick lines
_ZONE_FIELD_MM = 50.0  # nominal zone field length
_ZONE_TEXT_MM = 3.5  # zone letter/numeral height
_CENTRE_REACH_MM = 10.0  # centring mark reach past the drawing frame
_TITLE_BLOCK_W_MM = 180.0  # ISO 7200 recommended title-block width
_TITLE_ROW_MM = 13.0
_TITLE_ROWS = 3
_TITLE_GAP_MM = 8.0  # clearance between content and the title block
_ZONE_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # I and O excluded (ISO 5457 §4.4)


def _zone_letter(index: int) -> str:
    """Zone letter for a vertical-border field: A..Z, then AA, AB, ..."""
    if index < len(_ZONE_LETTERS):
        return _ZONE_LETTERS[index]
    over = index - len(_ZONE_LETTERS)
    return _ZONE_LETTERS[over // len(_ZONE_LETTERS)] + _ZONE_LETTERS[over % len(_ZONE_LETTERS)]


def _mm(value: float) -> float:
    """Millimetres to drawio units (drawio maps 100 px per inch on pages)."""
    return value * _PX_PER_MM


def _zone_spans(half: float) -> list[tuple[float, float]]:
    """Field spans on one half-side: ~50 mm fields outward from the sheet's
    symmetry axis; the corner field absorbs the remainder (ISO 5457 §4.4).
    The resulting counts reproduce ISO 5457 Table 2 on every A-size."""
    n = max(1, round((half / _PX_PER_MM) / _ZONE_FIELD_MM))
    bounds = [min(_mm(_ZONE_FIELD_MM) * i, half) for i in range(n)]
    bounds.append(half)
    return [(bounds[i], bounds[i + 1]) for i in range(n)]


def _zone_segments(center: float, half: float) -> list[tuple[float, float]]:
    """All field segments across a side, ordered edge to edge."""
    spans = _zone_spans(half)
    left = [(center - b, center - a) for a, b in reversed(spans)]
    right = [(center + a, center + b) for a, b in spans]
    return left + right


def _zone_ticks(center: float, half: float) -> list[float]:
    """Internal field boundaries (the symmetry axis takes the centring mark)."""
    spans = _zone_spans(half)
    return [center - a for a, _b in spans if a > 0] + [center + a for a, _b in spans if a > 0]


def _frame_geometry(content_w: float, content_h: float) -> dict[str, Any]:
    """ISO 5457 sheet + frame layout for the pin-table content.

    Picks the smallest sheet whose drawing space (sheet minus the 20 mm
    filing border and 10 mm borders) holds the content plus the ISO 7200
    title block, which anchors bottom-right; when the sheet is wide enough
    the title block may share the bottom row without a reserved strip.
    Content taller than A0x3 falls back to a custom sheet sized the same
    way — the frame marks are identical, only the size designation differs.
    """
    lm = _mm(_BORDER_LEFT_MM)
    tm = bm = rm = _mm(_BORDER_MM)
    tb_w = _mm(_TITLE_BLOCK_W_MM)
    tb_h = _TITLE_ROWS * _mm(_TITLE_ROW_MM)
    gap = _mm(_TITLE_GAP_MM)

    def fits(sheet_w: float, sheet_h: float) -> bool:
        ds_w, ds_h = sheet_w - lm - rm, sheet_h - tm - bm
        side_by_side = content_w + tb_w + gap <= ds_w
        need_h = content_h + (0.0 if side_by_side else tb_h + gap)
        return ds_w >= max(content_w, tb_w) and ds_h >= need_h

    name, sheet_w, sheet_h = "", 0.0, 0.0
    for sheet_name, w_mm, h_mm in _SHEETS:
        w, h = round(_mm(w_mm)), round(_mm(h_mm))
        if fits(w, h):
            name, sheet_w, sheet_h = sheet_name, w, h
            break
    if not name:
        ds_w, ds_h = max(content_w, tb_w), content_h + tb_h + gap
        sheet_w, sheet_h = ds_w + lm + rm, ds_h + tm + bm
        # No A-series designation exists; the corner still needs a size
        # designation, so carry the real millimetre dimensions.
        name = f"{round(sheet_w / _PX_PER_MM)}x{round(sheet_h / _PX_PER_MM)}"
    ds = (lm, tm, sheet_w - lm - rm, sheet_h - tm - bm)
    tb = (sheet_w - rm - tb_w, sheet_h - bm - tb_h, tb_w, tb_h)
    return {"name": name, "w": sheet_w, "h": sheet_h, "ds": ds, "tb": tb}


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


# Insulation colors whose strokes wash out on the white sheet get a dark
# underlay edge so the wire stays visible (WH white, YE pale yellow).
_PALE_LUMINANCE = 0.65


def _stroke_luminance(hex_color: str) -> float:
    c = hex_color.lstrip("#")
    r, g, b = (int(c[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _net_label(net: HarnessNet) -> str:
    return f"{net.id} ({net.ref})" if net.ref else net.id


def _wire_label(wire: HarnessWire, wtype: WireType, net: HarnessNet) -> str:
    color = f"{wire.color} " if wire.color else ""
    label = (
        f"{wire.id} · {color}{wtype.name} · "
        f"{_net_label(net)}/{net.signal_class} · {_num(wire.length_m)}m"
    )
    if net.twisted_pair_with is not None:
        label += f" · TP\u21c4{net.twisted_pair_with}"
    return label


def _diagram_title(contract: HarnessContract) -> str:
    return f"{contract.name} · {contract.contract_id} · rev {contract.revision}"


def _doc_legend_rows() -> list[str]:
    return [
        "wire stroke = insulation color",
        "  RD/BK = red base, black stripe",
        "  uncolored = signal-class color",
        "dark halo  = pale insulation (edge)",
        "dashed wire = shielded wire type",
        "grey cavity = unused cavity",
        "black dot   = splice (kind label)",
        "grey band   = twisted-pair link",
        "edge bump   = same-connector loop",
        "key <x>    = connector keying",
        "label = id·color type·net/class·m",
    ]


def _doc_notes_rows(contract: HarnessContract, unused_cavities: int) -> list[str]:
    """Manufacturing notes the shop floor needs without design context."""
    lines = [
        f"build+inspect: IPC-A-620 cl.{contract.ipc_class}",
        f"ambient service {_num(contract.ambient_temperature_c)} °C",
        "units: wire m, strip mm, cavity mm2",
        "wire list: wire-list.csv",
        "cut/strip/crimp: cut-table.csv",
        "parts list: bom.csv",
    ]
    for route in sorted(contract.routes, key=lambda r: r.id):
        total = sum(seg.length_m for seg in route.segments)
        parts = [route.id, f"{len(route.segments)}seg", f"{_num(total)}m", route.protection]
        bends = [
            seg.min_bend_radius_mm for seg in route.segments if seg.min_bend_radius_mm is not None
        ]
        if bends:
            parts.append(f"bend>={_num(min(bends))}mm")
        if route.flex_required:
            parts.append("flex")
        if route.anchors:
            parts.append("anchors " + ",".join(sorted(route.anchors)))
        lines.append("route " + " · ".join(parts))
    for splice in sorted(contract.splices, key=lambda s: s.id):
        lines.append(f"splice {splice.id} {splice.kind}")
    nets = contract.net_map()
    for net in sorted(contract.nets, key=lambda n: n.id):
        peer = net.twisted_pair_with
        if peer is not None and peer >= net.id and peer in nets:
            lines.append(f"twisted {_net_label(net)}⇄{_net_label(nets[peer])}")
        if net.shield_required:
            lines.append(f"net {_net_label(net)} shielded")
    if contract.service is not None:
        service: list[str] = []
        if contract.service.mating_cycles is not None:
            service.append(f"{contract.service.mating_cycles} mating")
        if contract.service.flex_cycles is not None:
            service.append(f"{contract.service.flex_cycles} flex")
        if service:
            lines.append("service " + " / ".join(service) + " cycles")
    if unused_cavities:
        lines.append(f"{unused_cavities} cav. unused (grey); seal per spec")
    return [f"{i}. {line}" for i, line in enumerate(lines, start=1)]


def _doc_block(
    block_id: str, header: str, rows: list[str], x: float, y: float, w: float
) -> dict[str, Any]:
    return {
        "id": block_id,
        "header": header,
        "rows": rows,
        "x": x,
        "y": y,
        "w": w,
        "h": _DOC_HEADER_H + len(rows) * _DOC_ROW_H + _DOC_PAD_BOTTOM,
    }


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


def _frame_cells(frame: dict[str, Any]) -> list[str]:
    """mxCell fragments for the frame layer: sheet edge, drawing-space
    frame, centring marks, the grid-reference zone system, the sheet-size
    designation, and the ISO 7200 title block."""
    sw, sh = frame["w"], frame["h"]
    ds_x, ds_y, ds_w, ds_h = frame["ds"]
    tb_x, tb_y, tb_w, tb_h = frame["tb"]
    rm, bm = _mm(_BORDER_MM), _mm(_BORDER_MM)
    grid = _mm(_GRID_STROKE_MM)
    thick = _mm(_FRAME_STROKE_MM)
    reach = _mm(_CENTRE_REACH_MM)
    cx, cy = sw / 2, sh / 2

    def rect(cid: str, x: float, y: float, w: float, h: float, style: str) -> str:
        return (
            f'<mxCell id="{cid}" value="" style="{style}" vertex="1" parent="frame">'
            f'<mxGeometry x="{_num(x)}" y="{_num(y)}" width="{_num(w)}" '
            f'height="{_num(h)}" as="geometry" /></mxCell>'
        )

    def text(cid: str, value: str, x: float, y: float, w: float, h: float, extra: str) -> str:
        return (
            f'<mxCell id="{cid}" value="{value}" '
            f'style="text;strokeColor=none;fillColor=none;align=center;'
            f'verticalAlign=middle;fontFamily=monospace;{extra}" '
            f'vertex="1" parent="frame">'
            f'<mxGeometry x="{_num(x)}" y="{_num(y)}" width="{_num(w)}" '
            f'height="{_num(h)}" as="geometry" /></mxCell>'
        )

    fill = "rounded=0;fillColor=#000000;strokeColor=none;"
    frame_style = f"rounded=0;fillColor=none;strokeColor=#000000;strokeWidth={_num(thick)};"
    sheet_style = "rounded=0;fillColor=none;strokeColor=#000000;strokeWidth=0.5;"
    parts = [
        rect("frame-sheet", 0.0, 0.0, sw, sh, sheet_style),
        # Centring marks: at the ends of the sheet's symmetry axes, reaching
        # 10 mm past the drawing frame into the drawing space (§4.3).
        rect("frame-cmark-left", 0.0, cy - thick / 2, ds_x + reach, thick, fill),
        rect("frame-cmark-right", sw - rm - reach, cy - thick / 2, rm + reach, thick, fill),
        rect("frame-cmark-top", cx - thick / 2, 0.0, thick, ds_y + reach, fill),
        rect("frame-cmark-bottom", cx - thick / 2, sh - bm - reach, thick, bm + reach, fill),
        # Drawing-space frame (0.7 mm).
        rect("frame-border", ds_x, ds_y, ds_w, ds_h, frame_style),
    ]

    # Grid-reference system (§4.4): numerals left→right on the top and
    # bottom borders, capital letters top→bottom on both side borders.
    label_h = _mm(_ZONE_TEXT_MM)
    tick_style = fill
    for axis, strip_y0, strip_h in (("t", 0.0, ds_y), ("b", sh - bm, bm)):
        for i, pos in enumerate(_zone_ticks(cx, sw / 2)):
            parts.append(
                rect(
                    f"frame-tick-{axis}{i}",
                    pos - grid / 2,
                    strip_y0,
                    grid,
                    strip_h,
                    tick_style,
                )
            )
        for i, (x0, x1) in enumerate(_zone_segments(cx, sw / 2)):
            parts.append(
                text(
                    f"frame-lab-{axis}{i}",
                    str(i + 1),
                    x0,
                    strip_y0,
                    x1 - x0,
                    strip_h,
                    f"fontSize={_num(label_h)};",
                )
            )
    for axis, strip_x0, strip_w in (("l", 0.0, ds_x), ("r", sw - rm, rm)):
        for i, pos in enumerate(_zone_ticks(cy, sh / 2)):
            parts.append(
                rect(
                    f"frame-tick-{axis}{i}",
                    strip_x0,
                    pos - grid / 2,
                    strip_w,
                    grid,
                    tick_style,
                )
            )
        for i, (y0, y1) in enumerate(_zone_segments(cy, sh / 2)):
            parts.append(
                text(
                    f"frame-lab-{axis}{i}",
                    _zone_letter(i),
                    strip_x0,
                    y0,
                    strip_w,
                    y1 - y0,
                    f"fontSize={_num(label_h)};",
                )
            )

    # Size designation in the bottom border at the right corner (§5).
    parts.append(
        text(
            "frame-size",
            _esc(frame["name"]),
            sw - _mm(46.0),
            sh - bm,
            _mm(42.0),
            bm,
            "fontSize=10;fontStyle=1;align=right;",
        )
    )

    # ISO 7200 title block, bottom-right of the drawing space. Fields are
    # contract-derived only — no wall-clock data, so the artifact stays
    # byte-deterministic; "Date of issue" is an em dash placeholder.
    fields = [
        [
            ("Legal owner", "VibeBB"),
            ("Title", _esc(frame["title"])),
            ("Drawing no.", _esc(frame["drawing_no"])),
            ("Rev.", _esc(frame["revision"])),
        ],
        [
            ("Scale", "NTS"),
            ("Sheet", "1/1"),
            ("Size", _esc(frame["name"])),
            ("IPC class", str(frame["ipc_class"])),
        ],
        [
            ("Drawn by", _esc(frame["drawn_by"])),
            ("Document type", "wire harness pin table"),
            ("Date of issue", "—"),
            ("Units", "px = 0.254 mm"),
        ],
    ]
    col_w, row_h = tb_w / 4, _mm(_TITLE_ROW_MM)
    lab_h = row_h * 0.45
    for row, entries in enumerate(fields):
        for col, (label, value) in enumerate(entries):
            x, y = tb_x + col * col_w, tb_y + row * row_h
            cell_id = f"tb-{row}{col}"
            # Plain-text caption/value pairs keep the model free of HTML
            # labels so drawio exports SVG text instead of foreignObjects.
            parts.append(
                f'<mxCell id="{cell_id}" value="" '
                'style="rounded=0;whiteSpace=wrap;strokeColor=#000000;'
                'strokeWidth=1;fillColor=none;" vertex="1" parent="frame">'
                f'<mxGeometry x="{_num(x)}" y="{_num(y)}" '
                f'width="{_num(col_w)}" height="{_num(row_h)}" as="geometry" /></mxCell>'
            )
            parts.append(
                f'<mxCell id="{cell_id}-lab" value="{label}" '
                'style="text;align=left;verticalAlign=middle;spacingLeft=4;'
                'fontFamily=monospace;fontSize=6;" vertex="1" parent="frame">'
                f'<mxGeometry x="{_num(x)}" y="{_num(y)}" '
                f'width="{_num(col_w)}" height="{_num(lab_h)}" as="geometry" /></mxCell>'
            )
            parts.append(
                f'<mxCell id="{cell_id}-val" value="{value}" '
                'style="text;align=left;verticalAlign=middle;spacingLeft=4;'
                'fontFamily=monospace;fontSize=10;fontStyle=1;" vertex="1" parent="frame">'
                f'<mxGeometry x="{_num(x)}" y="{_num(y + lab_h)}" '
                f'width="{_num(col_w)}" height="{_num(row_h - lab_h)}" as="geometry" /></mxCell>'
            )
    parts.append(rect("tb-outer", tb_x, tb_y, tb_w, tb_h, frame_style))
    return parts


def _diagram_layout(contract: HarnessContract) -> dict[str, Any]:
    """Shared geometry for the SVG body and the embedded drawio model."""
    positions, column_of, page_w, page_h = _diagram_geometry(contract)
    used = {
        (endpoint.connector, endpoint.cavity)
        for wire in contract.wires
        for endpoint in (wire.from_endpoint, wire.to_endpoint)
        if endpoint.connector is not None
    }
    all_cavities = {
        (connector.id, cavity.id)
        for connector in contract.connectors
        for cavity in connector.cavities
    }
    # The legend/notes strip is drawing content: it must be measured before
    # the frame picks a sheet, then shifted into the drawing space with the
    # pin table. It sits in the strip below the table (the notes position on
    # a conventional drawing).
    doc_y = page_h - 60.0 + _DOC_GAP_TOP
    doc_blocks = [
        _doc_block("doc-legend", "LEGEND", _doc_legend_rows(), _DOC_LEGEND_X, doc_y, _DOC_LEGEND_W),
        _doc_block(
            "doc-notes",
            "NOTES",
            _doc_notes_rows(contract, len(all_cavities - used)),
            _DOC_NOTES_X,
            doc_y,
            _DOC_NOTES_W,
        ),
    ]
    content_h = max(page_h, doc_y + max(block["h"] for block in doc_blocks) + 40.0)
    frame = _frame_geometry(page_w, content_h)
    frame["title"] = contract.name
    frame["drawing_no"] = contract.contract_id
    frame["revision"] = contract.revision
    frame["ipc_class"] = contract.ipc_class
    frame["drawn_by"] = f"wire-agent/{__version__}"
    offset_x, offset_y = frame["ds"][0], frame["ds"][1]
    positions = {cid: (x + offset_x, y + offset_y) for cid, (x, y) in positions.items()}
    for block in doc_blocks:
        block["x"] += offset_x
        block["y"] += offset_y
    connectors = contract.connector_map()
    cavity_y: dict[tuple[str, str], float] = {}
    for connector in contract.connectors:
        _x, y = positions[connector.id]
        for idx, cavity in enumerate(connector.cavities):
            cavity_y[(connector.id, cavity.id)] = y + _HEADER_H + idx * _ROW_H + _ROW_H / 2
    splice_pos = _splice_positions(contract, cavity_y)
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
        "page_h": content_h,
        "frame": frame,
        "doc_blocks": doc_blocks,
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


def _label_channel_offset(
    wire: HarnessWire, layout: dict[str, Any], bump: tuple[float, float] | None
) -> float:
    """Horizontal label offset pushing a wire label off the connector edge
    into the routing channel.

    A label anchors at its edge midpoint: for loops and for wires between
    connectors in the same column that midpoint sits on the connector
    boundary, so the text prints over the connector (the observed W4-C3
    collision). Cross-column wires already anchor in the channel and keep
    offset 0.
    """
    column_of = layout["column_of"]
    fa, ta = wire.from_endpoint, wire.to_endpoint
    if bump is not None:
        conn = fa.connector
        if conn is None:
            return 0.0
        return (1.0 if column_of[conn] == 0 else -1.0) * 120.0
    if (
        fa.connector is None
        or ta.connector is None
        or column_of[fa.connector] != column_of[ta.connector]
    ):
        return 0.0
    col: int = column_of[fa.connector]
    x_edge: float = _COL_X[col] + (_CONN_W if col == 0 else 0.0)
    return _MID_CHANNEL_X - x_edge


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
    strokes, floating dashed twist-pair bands, and a bottom "frame" layer
    drawing the ISO 5457/JIS Z 8311 sheet frame and ISO 7200 title block.
    """
    positions = layout["positions"]
    column_of = layout["column_of"]
    used = layout["used_cavities"]
    frame = layout["frame"]
    parts = [
        '<mxGraphModel dx="0" dy="0" grid="1" gridSize="10" guides="1" '
        'tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" '
        f'pageWidth="{_num(frame["w"])}" pageHeight="{_num(frame["h"])}" math="0" shadow="0">',
        "<root>",
        '<mxCell id="0" />',
        '<mxCell id="frame" value="frame" parent="0" />',
        '<mxCell id="1" value="harness" parent="0" />',
        '<mxCell id="wires" value="wires" parent="0" />',
        *_frame_cells(frame),
        f'<mxCell id="title" value="{_esc(_diagram_title(contract))}" '
        'style="text;align=left;fontSize=14;fontFamily=monospace;" vertex="1" parent="1">'
        f'<mxGeometry x="{_num(frame["ds"][0] + _COL_X[0])}" y="{_num(frame["ds"][1] + 40)}" '
        f'width="{_num(layout["page_w"] - 2 * _COL_X[0])}" height="24" as="geometry" /></mxCell>',
    ]
    for block in layout["doc_blocks"]:
        parts.append(
            f'<mxCell id="{block["id"]}" value="{_esc(block["header"])}" '
            f'style="swimlane;startSize={_num(_DOC_HEADER_H)};whiteSpace=wrap;'
            "fillColor=#ffffff;strokeColor=#333333;fontFamily=monospace;fontSize=11;"
            'fontStyle=1;align=center;collapsible=0;container=1;recursiveResize=0;" '
            'vertex="1" parent="1">'
            f'<mxGeometry x="{_num(block["x"])}" y="{_num(block["y"])}" '
            f'width="{_num(block["w"])}" height="{_num(block["h"])}" '
            'as="geometry" /></mxCell>'
        )
        for i, row in enumerate(block["rows"]):
            parts.append(
                f'<mxCell id="{block["id"]}-r{i}" value="{_esc(row)}" '
                'style="text;align=left;verticalAlign=middle;spacingLeft=8;'
                'fontFamily=monospace;fontSize=10;" vertex="1" '
                f'parent="{block["id"]}">'
                f'<mxGeometry y="{_num(_DOC_HEADER_H + i * _DOC_ROW_H)}" '
                f'width="{_num(block["w"])}" height="{_num(_DOC_ROW_H)}" '
                'as="geometry" /></mxCell>'
            )
    for connector in sorted(contract.connectors, key=lambda c: c.id):
        x, y = positions[connector.id]
        header = f"{connector.id} · {connector.family} · {len(connector.cavities)}p"
        if connector.keying is not None:
            header += f" · key {connector.keying}"
        parts.append(
            f'<mxCell id="conn-{connector.id}" value="{_esc(header)}" '
            f'style="swimlane;startSize={_num(_HEADER_H)};whiteSpace=wrap;'
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
                f'style="rounded=0;whiteSpace=wrap;{free}'
                "strokeColor=#bbbbbb;fontFamily=monospace;fontSize=10;align=left;"
                f'spacingLeft=6;" vertex="1" parent="conn-{connector.id}">'
                f'<mxGeometry y="{_num(row_y)}" width="{_num(_CONN_W)}" '
                f'height="{_num(_ROW_H)}" as="geometry" /></mxCell>'
            )
    for splice in sorted(contract.splices, key=lambda s: s.id):
        sx, sy = layout["splice_pos"][splice.id]
        parts.append(
            f'<mxCell id="splice-{splice.id}" value="{_esc(splice.id)} · {splice.kind}" '
            'style="ellipse;fillColor=#333333;strokeColor=none;'
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
        label_x = _label_channel_offset(wire, layout, bump)
        label_offset = f'<mxPoint x="{_num(label_x)}" y="{_num(label_y)}" as="offset" />'
        # A pale insulation stroke (white, pale yellow) disappears on the
        # white sheet — give it a dark underlay edge first so the wire
        # keeps a visible silhouette (see LEGEND).
        if _stroke_luminance(color) >= _PALE_LUMINANCE:
            parts.append(
                f'<mxCell id="wire-{wire.id}-halo" value="" '
                'style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;'
                "jettySize=auto;strokeWidth=4.5;strokeColor=#3a3a3a;opacity=100;"
                f"{_endpoint_side(wire.from_endpoint, 'exit', column_of)}"
                f'{_endpoint_side(wire.to_endpoint, "entry", column_of)}" '
                'edge="1" parent="wires" '
                f'source="{_endpoint_cell_id(wire.from_endpoint)}" '
                f'target="{_endpoint_cell_id(wire.to_endpoint)}">'
                '<mxGeometry relative="1" as="geometry">'
                + _loop_points(bump)
                + "</mxGeometry></mxCell>"
            )
        parts.append(
            f'<mxCell id="wire-{wire.id}" value="{_esc(_wire_label(wire, wtype, net))}" '
            'style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;'
            f"jettySize=auto;strokeWidth=1.5;strokeColor={color};{dashed}"
            "fontFamily=monospace;fontSize=10;labelBackgroundColor=#ffffff;"
            f"{_endpoint_side(wire.from_endpoint, 'exit', column_of)}"
            f'{_endpoint_side(wire.to_endpoint, "entry", column_of)}" '
            'edge="1" parent="wires" '
            f'source="{_endpoint_cell_id(wire.from_endpoint)}" '
            f'target="{_endpoint_cell_id(wire.to_endpoint)}">'
            '<mxGeometry x="0" relative="1" as="geometry">'
            + label_offset
            + _loop_points(bump)
            + "</mxGeometry></mxCell>"
        )
        if stripe is not None:
            parts.append(
                f'<mxCell id="wire-{wire.id}-stripe" value="" '
                'style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;'
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
            'style="endArrow=none;rounded=0;dashed=1;strokeColor=#616161;'
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


def _drawio_cli() -> list[str]:
    """Headless drawio-desktop export prefix; fails closed when unavailable."""
    if shutil.which("drawio") is None or shutil.which("xvfb-run") is None:
        raise RuntimeError(
            "drawio export needs drawio-desktop and xvfb (both ship in the wire-tools image)"
        )
    return [
        "xvfb-run",
        "-a",
        "drawio",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--disable-update",
    ]


# Per-file export budget handed to drawio-desktop 31.5.2's ``--timeout``
# (the flag fails an export exceeding it and exits 1). The subprocess bound
# adds slack so a stuck Electron boot also terminates instead of hanging.
_DRAWIO_TIMEOUT_SECONDS = 300
_DRAWIO_SUBPROCESS_TIMEOUT = _DRAWIO_TIMEOUT_SECONDS + 120


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
    with tempfile.TemporaryDirectory(prefix="wire-drawio-") as tmp:
        src = Path(tmp) / "harness.drawio"
        out = Path(tmp) / "out"
        src.write_text(mxfile, encoding="utf-8")
        try:
            result = subprocess.run(
                [
                    *cmd,
                    "-x",
                    "--timeout",
                    str(_DRAWIO_TIMEOUT_SECONDS),
                    *fmt_args,
                    "-o",
                    str(out),
                    str(src),
                ],
                capture_output=True,
                check=False,
                timeout=_DRAWIO_SUBPROCESS_TIMEOUT,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"drawio -x {' '.join(fmt_args)} timed out after {_DRAWIO_SUBPROCESS_TIMEOUT}s"
            ) from exc
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
    argv = [*cmd, "-x", "--timeout", str(_DRAWIO_TIMEOUT_SECONDS)]
    if fmt is not None:
        argv += ["-f", fmt]
    if output_path is not None:
        argv += ["-o", str(output_path)]
    argv += [*options, str(input_path)]
    try:
        result = subprocess.run(
            argv, capture_output=True, check=False, timeout=_DRAWIO_SUBPROCESS_TIMEOUT
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"drawio -x timed out after {_DRAWIO_SUBPROCESS_TIMEOUT}s") from exc
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

    The diagram is rendered by drawio-desktop (canonical rendering,
    embedded model round-trips); it ships in the wire-tools image, and a
    missing drawio/xvfb fails the export rather than degrading the artifact.
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
    artifacts["harness-diagram.drawio.svg"] = _drawio_render(mxfile, ["-f", "svg", "-e"]).decode(
        "utf-8"
    )
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

    lint_report = drawio_lint.lint_text(mxfile, source=Path("harness-diagram.drawio"))
    lint_text_out = lint_report.model_dump_json(indent=2) + "\n"
    (out_dir / "harness-diagram.drawio_lint.json").write_text(lint_text_out, encoding="utf-8")
    files.append(
        {
            "path": "harness-diagram.drawio_lint.json",
            "sha256": hashlib.sha256(lint_text_out.encode("utf-8")).hexdigest(),
            "bytes": len(lint_text_out.encode("utf-8")),
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
        "diagram_renderer": "drawio-desktop",
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

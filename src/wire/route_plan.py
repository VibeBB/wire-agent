"""Route plan projection: routes drawn through mech-envelope anchors.

A top view (X/Y; Z is printed in each anchor label) of every imported
anchor that carries `position_mm`, with each route drawn as a polyline
through its anchors in declaration order. The drawing exists so a vision
reviewer can compare routing intent against the mechanical layout; the
`route_geometry` gate is the deterministic check on the same data.
Identical contracts produce identical mxfile text.
"""

from __future__ import annotations

import math
from itertools import pairwise

from .contract import AnchorPoint, HarnessContract, HarnessRoute
from .diagram import _esc  # pyright: ignore[reportPrivateUsage]

ROUTE_PLAN_NAME = "route-plan.drawio.svg"
ROUTE_PLAN_PNG = "route-plan.png"
_CANVAS_PX = 760.0
_MARGIN_PX = 80.0
_ANCHOR_PX = 18.0
_LABEL_PX = 240.0
_ROUTE_COLORS = ("#1565c0", "#c00000", "#2e7d32", "#6a3fb5", "#ef6c00", "#00838f")
_ANCHOR_SHAPES = {
    "clip": "ellipse;fillColor=#ffffff;strokeColor=#1a1a1a;",
    "grommet": "ellipse;shape=doubleEllipse;fillColor=#ffffff;strokeColor=#1a1a1a;",
    "breakout": "rhombus;fillColor=#fff3e0;strokeColor=#ef6c00;",
    "other": "rounded=0;fillColor=#eeeeee;strokeColor=#555555;",
}


def placed_anchors(contract: HarnessContract) -> dict[str, AnchorPoint]:
    return {
        name: point
        for name, point in sorted(contract.anchor_map().items())
        if point.position_mm is not None
    }


def _span_mm(route: HarnessRoute, placed: dict[str, AnchorPoint]) -> float | None:
    names = [name for name in route.anchors if name in placed]
    if len(names) < 2 or len(names) != len(route.anchors):
        return None
    total = 0.0
    for first, second in pairwise(names):
        a = placed[first].position_mm
        b = placed[second].position_mm
        assert a is not None and b is not None
        total += math.dist(a, b)
    return total


def route_plan_mxfile(contract: HarnessContract) -> str | None:
    """Drawio mxfile of the route plan, or None when no anchor has a position."""
    placed = placed_anchors(contract)
    if not placed:
        return None
    xs = [p.position_mm[0] for p in placed.values() if p.position_mm is not None]
    ys = [p.position_mm[1] for p in placed.values() if p.position_mm is not None]
    span = max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
    scale = _CANVAS_PX / span

    def at(point: AnchorPoint) -> tuple[float, float]:
        assert point.position_mm is not None
        x = _MARGIN_PX + (point.position_mm[0] - min(xs)) * scale
        # Drawio's y axis points down; flip so +Y in the envelope points up.
        y = _MARGIN_PX + (max(ys) - point.position_mm[1]) * scale
        return round(x, 2), round(y, 2)

    cells: list[str] = ['<mxCell id="0"/><mxCell id="1" parent="0"/>']
    title = (
        f"Route plan (top view X/Y, mm) — {contract.name} rev {contract.revision}"
        f" — scale {scale:.3f} px/mm"
    )
    cells.append(
        f'<mxCell id="title" value="{_esc(title)}" style="text;fontSize=14;fontStyle=1;'
        'align=left;" vertex="1" parent="1"><mxGeometry x="20" y="10" width="760" '
        'height="30" as="geometry"/></mxCell>'
    )
    for name, point in placed.items():
        x, y = at(point)
        assert point.position_mm is not None
        label = f"{name} ({point.kind}) z={point.position_mm[2]:g}"
        style = _ANCHOR_SHAPES[point.kind] + "html=0;whiteSpace=wrap;"
        cells.append(
            f'<mxCell id="anchor-{_esc(name)}" value="" style="{style}" vertex="1" parent="1">'
            f'<mxGeometry x="{x - _ANCHOR_PX / 2}" y="{y - _ANCHOR_PX / 2}" '
            f'width="{_ANCHOR_PX}" height="{_ANCHOR_PX}" as="geometry"/></mxCell>'
        )
        cells.append(
            f'<mxCell id="anchor-label-{_esc(name)}" value="{_esc(label)}" '
            'style="text;fontSize=11;align=left;verticalAlign=middle;whiteSpace=wrap;" '
            'vertex="1" parent="1">'
            f'<mxGeometry x="{x + _ANCHOR_PX}" y="{y - _ANCHOR_PX}" width="{_LABEL_PX}" '
            'height="36" '
            'as="geometry"/></mxCell>'
        )
    legend_y = _MARGIN_PX * 2 + _CANVAS_PX
    for index, route in enumerate(contract.routes):
        color = _ROUTE_COLORS[index % len(_ROUTE_COLORS)]
        length_mm = sum(segment.length_m for segment in route.segments) * 1000.0
        span = _span_mm(route, placed)
        span_text = "n/a" if span is None else f"{span:.0f} mm"
        verdict = "" if span is None else (" OK" if length_mm >= span else " TOO SHORT")
        anchors = [name for name in route.anchors if name in placed]
        for hop, (first, second) in enumerate(pairwise(anchors)):
            cells.append(
                f'<mxCell id="route-{route.id}-{hop}" value="{route.id if hop == 0 else ""}" '
                f'style="endArrow=none;html=0;strokeWidth=3;strokeColor={color};'
                'fontSize=11;labelBackgroundColor=#ffffff;" edge="1" parent="1" '
                f'source="anchor-{_esc(first)}" target="anchor-{_esc(second)}">'
                '<mxGeometry relative="1" as="geometry"/></mxCell>'
            )
        legend = (
            f"{route.id}: {' > '.join(route.anchors) or 'no anchors'} | length "
            f"{length_mm:.0f} mm | anchor span {span_text}{verdict} | protection "
            f"{route.protection}{' | flex' if route.flex_required else ''}"
        )
        cells.append(
            f'<mxCell id="legend-{route.id}" value="{_esc(legend)}" '
            f'style="text;fontSize=12;align=left;fontColor={color};" vertex="1" parent="1">'
            f'<mxGeometry x="20" y="{legend_y + index * 22}" width="900" height="20" '
            'as="geometry"/></mxCell>'
        )
    model = (
        f'<mxGraphModel dx="1000" dy="1000" grid="0" page="1" '
        f'pageWidth="{int(_MARGIN_PX * 2 + _CANVAS_PX + _LABEL_PX)}" '
        f'pageHeight="{int(legend_y + 40 + 22 * len(contract.routes))}">'
        f"<root>{''.join(cells)}</root></mxGraphModel>"
    )
    return (
        '<mxfile host="wire-agent" type="device">'
        f'<diagram id="route-plan" name="route plan">{model}</diagram></mxfile>'
    )

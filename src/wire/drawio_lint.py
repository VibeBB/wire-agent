"""Deterministic readability lint for drawio mxfile diagrams.

Advisory companion to the gates: it inspects the generated
harness-diagram.drawio model (mxGraphModel XML) for readability and
model-integrity issues — unconnected edges, out-of-bounds or overlapping
cells, cavities overflowing their connector swimlane, unlabeled cells.
It never promotes a verdict: errors mean the emitted model is broken
(fail-closed for the lint itself), warnings are review aids.
"""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DrawioLintError(ValueError):
    """Raised when a drawio file cannot be linted."""


class DrawioLintFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    severity: Literal["error", "warning"]
    description: str
    items: list[str] = Field(default_factory=lambda: list[str]())


class DrawioLintReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["drawio_lint"] = "drawio_lint"
    source: Path
    verdict: Literal["pass", "fail"]
    errors: int
    warnings: int
    cells_checked: int
    findings: list[DrawioLintFinding] = Field(default_factory=lambda: list[DrawioLintFinding]())


_MIN_PAGE_USAGE = 0.30
_OVERLAP_EPSILON = 1.0  # sq px — touching edges are fine, real overlaps are not


@dataclass(frozen=True)
class _Cell:
    id: str
    value: str
    parent: str | None
    vertex: bool
    edge: bool
    source: str | None
    target: str | None
    floating: bool
    x: float | None
    y: float | None
    width: float | None
    height: float | None


def _cells(root: ET.Element) -> list[_Cell]:
    cells: list[_Cell] = []
    for cell in root.iter("mxCell"):
        geo = cell.find("mxGeometry")
        x = y = width = height = None
        floating = False
        if geo is not None:
            points = {p.get("as") for p in geo.findall("mxPoint")}
            floating = {"sourcePoint", "targetPoint"} <= points
            try:
                x = float(geo.get("x", "0") or 0)
                y = float(geo.get("y", "0") or 0)
                width = float(geo.get("width", "0") or 0)
                height = float(geo.get("height", "0") or 0)
            except ValueError:
                pass
        cells.append(
            _Cell(
                id=cell.get("id", ""),
                value=cell.get("value", "") or "",
                parent=cell.get("parent"),
                vertex=cell.get("vertex") == "1",
                edge=cell.get("edge") == "1",
                source=cell.get("source"),
                target=cell.get("target"),
                floating=floating,
                x=x,
                y=y,
                width=width,
                height=height,
            )
        )
    return cells


def _page_size(model: ET.Element) -> tuple[float, float]:
    try:
        return float(model.get("pageWidth", "0") or 0), float(model.get("pageHeight", "0") or 0)
    except ValueError:
        return 0.0, 0.0


def _overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    width = min(ax + aw, bx + bw) - max(ax, bx)
    height = min(ay + ah, by + bh) - max(ay, by)
    return width * height if width > 0 and height > 0 else 0.0


def lint_text(text: str, *, source: Path) -> DrawioLintReport:
    try:
        mxfile = ET.fromstring(text)
    except ET.ParseError as exc:
        raise DrawioLintError(f"could not parse drawio XML: {exc}") from exc
    model = mxfile if mxfile.tag == "mxGraphModel" else mxfile.find(".//mxGraphModel")
    if model is None:
        raise DrawioLintError("no mxGraphModel element found")
    page_w, page_h = _page_size(model)
    cells = _cells(model)
    by_id = {cell.id: cell for cell in cells if cell.id}
    findings: list[DrawioLintFinding] = []

    for cell in cells:
        if not cell.edge:
            continue
        if not cell.source or not cell.target:
            # Floating edges anchor to absolute mxPoints, not cells
            # (e.g. twist-pair bands): valid drawio, not missing endpoints.
            if cell.floating:
                continue
            findings.append(
                DrawioLintFinding(
                    type="edge_missing_endpoints",
                    severity="error",
                    description=f"edge {cell.id} lacks source or target",
                    items=[cell.id],
                )
            )
            continue
        unknown = [end for end in (cell.source, cell.target) if end not in by_id]
        if unknown:
            findings.append(
                DrawioLintFinding(
                    type="edge_unknown_endpoint",
                    severity="error",
                    description=f"edge {cell.id} references unknown cells: {', '.join(unknown)}",
                    items=[cell.id],
                )
            )
        if cell.source == cell.target:
            findings.append(
                DrawioLintFinding(
                    type="edge_self_loop",
                    severity="warning",
                    description=f"edge {cell.id} connects a cell to itself",
                    items=[cell.id],
                )
            )

    # geometry checks for top-level vertices (parent is the root cell "1")
    boxes: dict[str, tuple[float, float, float, float]] = {}
    for cell in cells:
        if not cell.vertex or cell.parent != "1" or cell.id in {"1", "wires"}:
            continue
        if cell.x is None or cell.y is None or cell.width is None or cell.height is None:
            continue
        boxes[cell.id] = (cell.x, cell.y, cell.width, cell.height)
        if page_w and page_h:
            out = (
                cell.x < 0
                or cell.y < 0
                or cell.x + cell.width > page_w
                or cell.y + cell.height > page_h
            )
            if out:
                findings.append(
                    DrawioLintFinding(
                        type="vertex_out_of_bounds",
                        severity="error",
                        description=(
                            f"{cell.id} at ({cell.x:.0f},{cell.y:.0f}) "
                            f"{cell.width:.0f}x{cell.height:.0f} exceeds the "
                            f"{page_w:.0f}x{page_h:.0f}px page"
                        ),
                        items=[cell.id],
                    )
                )
        if not cell.value.strip():
            findings.append(
                DrawioLintFinding(
                    type="unlabeled_vertex",
                    severity="warning",
                    description=f"vertex {cell.id} has no label",
                    items=[cell.id],
                )
            )

    ids = list(boxes)
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            area = _overlap(boxes[a], boxes[b])
            if area > _OVERLAP_EPSILON:
                findings.append(
                    DrawioLintFinding(
                        type="vertex_overlap",
                        severity="warning",
                        description=(
                            f"{a} and {b} overlap by {area:.0f} px^2; labels may be unreadable"
                        ),
                        items=[a, b],
                    )
                )

    # children must fit inside their parent container
    for cell in cells:
        if not cell.vertex or cell.parent not in by_id:
            continue
        parent = by_id[cell.parent]
        if (
            parent.vertex
            and cell.y is not None
            and cell.height is not None
            and parent.height is not None
            and cell.y + cell.height > parent.height
        ):
            findings.append(
                DrawioLintFinding(
                    type="container_overflow",
                    severity="warning",
                    description=(
                        f"{cell.id} extends past its container {parent.id} "
                        f"({cell.y + cell.height:.0f} > {parent.height:.0f}px)"
                    ),
                    items=[cell.id, parent.id],
                )
            )

    # a connector/splice vertex whose no edge endpoint touches is drawn but unused
    edge_ends = {end for cell in cells if cell.edge for end in (cell.source, cell.target) if end}
    wired_parents = {by_id[e].parent for e in edge_ends if e in by_id}
    for cell in cells:
        if (
            cell.vertex
            and cell.parent == "1"
            and cell.id.startswith(("conn-", "splice-"))
            and cell.id not in wired_parents
        ):
            findings.append(
                DrawioLintFinding(
                    type="unconnected_container",
                    severity="warning",
                    description=f"{cell.id} has no wire endpoints; drawn but unused",
                    items=[cell.id],
                )
            )

    # A framed sheet deliberately holds whitespace for the drawing frame,
    # zone grid, and title block — coverage rules do not apply to it.
    framed = any(cell.id == "frame" and cell.parent == "0" for cell in cells)
    if page_w and page_h and len(boxes) >= 2 and not framed:
        xs = [b[0] for b in boxes.values()]
        ys = [b[1] for b in boxes.values()]
        x2 = [b[0] + b[2] for b in boxes.values()]
        y2 = [b[1] + b[3] for b in boxes.values()]
        usage = ((max(x2) - min(xs)) * (max(y2) - min(ys))) / (page_w * page_h)
        if usage < _MIN_PAGE_USAGE:
            findings.append(
                DrawioLintFinding(
                    type="page_underutilized",
                    severity="warning",
                    description=(
                        f"placed cells cover {usage * 100:.0f}% of the page; "
                        "spread placement for readability"
                    ),
                )
            )

    errors = sum(1 for f in findings if f.severity == "error")
    warnings = sum(1 for f in findings if f.severity == "warning")
    return DrawioLintReport(
        source=source,
        verdict="fail" if errors else "pass",
        errors=errors,
        warnings=warnings,
        cells_checked=sum(1 for cell in cells if cell.vertex or cell.edge),
        findings=findings,
    )


def lint_file(path: Path, output: Path | None = None) -> DrawioLintReport:
    try:
        text = path.read_text(encoding="utf-8")
        report = lint_text(text, source=path)
    except (OSError, DrawioLintError) as exc:
        report = DrawioLintReport(
            source=path,
            verdict="fail",
            errors=1,
            warnings=0,
            cells_checked=0,
            findings=[
                DrawioLintFinding(
                    type="parse_error",
                    severity="error",
                    description=str(exc),
                )
            ],
        )
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Advisory readability lint for drawio files")
    parser.add_argument("diagram", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    report = lint_file(args.diagram, args.output)
    print(report.model_dump_json(indent=2))
    return 0 if report.verdict == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

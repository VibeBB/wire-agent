"""Drawio lint tests — advisory readability checks on the mxfile model."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from helpers import example_contract_data
from wire.contract import HarnessContract
from wire.drawio_lint import DrawioLintError, DrawioLintReport, lint_file, lint_text
from wire.export import export_design
from wire.gates import run_gates
from wire.report import write_report


def _mxfile(body: str, page_w: int = 400, page_h: int = 300) -> str:
    return (
        '<mxfile host="wire-agent" type="device"><diagram id="d" name="d">'
        f'<mxGraphModel page="1" pageWidth="{page_w}" pageHeight="{page_h}">'
        f'<root><mxCell id="0" /><mxCell id="1" value="harness" parent="0" />{body}'
        "</root></mxGraphModel></diagram></mxfile>"
    )


def _vertex(
    cid: str, x: float, y: float, w: float = 200, h: float = 50, value: str = "v", parent: str = "1"
) -> str:
    return (
        f'<mxCell id="{cid}" value="{value}" vertex="1" parent="{parent}">'
        f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry" /></mxCell>'
    )


def _edge(cid: str, source: str | None, target: str | None) -> str:
    src = f' source="{source}"' if source else ""
    tgt = f' target="{target}"' if target else ""
    return (
        f'<mxCell id="{cid}" value="w" edge="1" parent="1"{src}{tgt}>'
        '<mxGeometry relative="1" as="geometry" /></mxCell>'
    )


def _lint(body: str, **kwargs: int) -> DrawioLintReport:
    return lint_text(_mxfile(body, **kwargs), source=Path("d.drawio"))


requires_drawio = pytest.mark.skipif(
    shutil.which("drawio") is None or shutil.which("xvfb-run") is None,
    reason="export needs drawio-desktop + xvfb (both ship in the wire-tools image)",
)


@requires_drawio
def test_generated_diagram_lints_clean(tmp_path: Path) -> None:
    contract = HarnessContract.model_validate(example_contract_data())
    export_design(contract, tmp_path)
    lint_path = tmp_path / "harness-diagram.drawio_lint.json"
    assert lint_path.is_file()
    report = DrawioLintReport.model_validate_json(lint_path.read_text(encoding="utf-8"))
    assert report.verdict == "pass"
    assert report.errors == 0
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert "harness-diagram.drawio_lint.json" in {f["path"] for f in manifest["files"]}


def test_parse_error_fails_closed(tmp_path: Path) -> None:
    bad = tmp_path / "bad.drawio"
    bad.write_text("<mxfile><unclosed", encoding="utf-8")
    report = lint_file(bad)
    assert report.verdict == "fail"
    assert report.findings[0].type == "parse_error"
    with pytest.raises(DrawioLintError):
        lint_text("<mxfile><unclosed", source=bad)


def test_missing_model_fails_closed(tmp_path: Path) -> None:
    bad = tmp_path / "bad.drawio"
    bad.write_text("<mxfile><diagram /></mxfile>", encoding="utf-8")
    report = lint_file(bad)
    assert report.verdict == "fail"
    assert report.findings[0].type == "parse_error"


def test_edge_missing_endpoints_is_error() -> None:
    report = _lint(_edge("w1", None, None))
    assert report.verdict == "fail"
    assert report.findings[0].type == "edge_missing_endpoints"


def test_edge_unknown_endpoint_is_error() -> None:
    body = _vertex("conn-C1", 10, 10) + _edge("w1", "conn-C1", "cav-C1:9")
    report = _lint(body)
    assert report.verdict == "fail"
    assert report.findings[0].type == "edge_unknown_endpoint"


def test_edge_self_loop_is_warning() -> None:
    body = _vertex("conn-C1", 10, 10) + _edge("w1", "conn-C1", "conn-C1")
    report = _lint(body)
    assert report.verdict == "pass"
    assert report.findings[0].type == "edge_self_loop"


def test_vertex_out_of_bounds_is_error() -> None:
    report = _lint(_vertex("conn-C1", 10, 10, w=800, h=50))
    assert report.verdict == "fail"
    assert report.findings[0].type == "vertex_out_of_bounds"


def test_overlapping_vertices_warn() -> None:
    body = _vertex("conn-C1", 10, 10) + _vertex("conn-C2", 50, 30)
    report = _lint(body)
    assert report.verdict == "pass"
    types = {f.type for f in report.findings}
    assert "vertex_overlap" in types


def test_container_overflow_warns() -> None:
    parent = _vertex("conn-C1", 10, 10, h=50)
    child = (
        '<mxCell id="cav-C1:9" value="9" vertex="1" parent="conn-C1">'
        '<mxGeometry y="40" width="200" height="22" as="geometry" /></mxCell>'
    )
    report = _lint(parent + child)
    assert report.verdict == "pass"
    assert any(f.type == "container_overflow" for f in report.findings)


def test_unlabeled_vertex_warns() -> None:
    report = _lint(_vertex("conn-C1", 10, 10, value=""))
    assert report.verdict == "pass"
    assert report.findings[0].type == "unlabeled_vertex"


def test_unconnected_container_warns() -> None:
    body = _vertex("conn-C1", 10, 10) + _vertex("conn-C2", 10, 100)
    body += _edge("w1", "conn-C1", "conn-C1")
    report = _lint(body)
    assert any(f.type == "unconnected_container" and "conn-C2" in f.items for f in report.findings)


def test_page_underutilized_warns() -> None:
    body = _vertex("conn-C1", 10, 10, w=40, h=30) + _vertex("conn-C2", 60, 10, w=40, h=30)
    body += _edge("w1", "conn-C1", "conn-C2")
    report = _lint(body, page_w=1200, page_h=900)
    assert any(f.type == "page_underutilized" for f in report.findings)


def test_page_underutilized_skipped_on_framed_sheet() -> None:
    """A framed sheet intentionally holds margins/zone grid/title block —
    coverage checks do not apply."""
    body = '<mxCell id="frame" value="frame" parent="0" />'
    body += _vertex("conn-C1", 10, 10, w=40, h=30) + _vertex("conn-C2", 60, 10, w=40, h=30)
    body += _edge("w1", "conn-C1", "conn-C2")
    report = _lint(body, page_w=1200, page_h=900)
    assert not any(f.type == "page_underutilized" for f in report.findings)


def test_floating_edge_is_not_missing_endpoints() -> None:
    """Edges anchored to absolute mxPoints (twist-pair bands) need no
    source/target cell — drawio draws them fine."""
    floating = (
        '<mxCell id="twist-0" value="tp" edge="1" parent="wires">'
        '<mxGeometry relative="1" as="geometry">'
        '<mxPoint x="10" y="10" as="sourcePoint" />'
        '<mxPoint x="90" y="90" as="targetPoint" />'
        "</mxGeometry></mxCell>"
    )
    report = _lint(floating)
    assert not any(f.type == "edge_missing_endpoints" for f in report.findings)


def _connector_column() -> str:
    """Two stacked connectors in one column with one cavity each."""
    conns = _vertex("conn-C1", 60, 100, w=200, h=70) + _vertex("conn-C3", 60, 170, w=200, h=70)
    cav1 = (
        '<mxCell id="cav-C1:1" value="1" vertex="1" parent="conn-C1">'
        '<mxGeometry y="26" width="200" height="22" as="geometry" /></mxCell>'
    )
    cav3 = (
        '<mxCell id="cav-C3:1" value="1" vertex="1" parent="conn-C3">'
        '<mxGeometry y="26" width="200" height="22" as="geometry" /></mxCell>'
    )
    return conns + cav1 + cav3


def _labeled_wire(value: str, offset_x: float = 0.0) -> str:
    return (
        f'<mxCell id="wire-W4" value="{value}" edge="1" parent="wires" '
        'source="cav-C1:1" target="cav-C3:1" '
        'style="exitX=1;exitY=0.5;entryX=1;entryY=0.5;">'
        '<mxGeometry relative="1" as="geometry">'
        f'<mxPoint x="{offset_x}" y="10" as="offset" />'
        "</mxGeometry></mxCell>"
    )


def test_wire_label_on_connector_warns() -> None:
    """A same-column wire's label anchors on the connector boundary —
    it must be pushed into the channel or it prints over the block."""
    report = _lint(_connector_column() + _labeled_wire("W4 · WH FLRY-B 0.35"))
    assert any(
        f.type == "label_on_connector" and f.items == ["wire-W4", "conn-C3"]
        for f in report.findings
    )


def test_wire_label_in_channel_lints_clean() -> None:
    """A channel-shifted label clears every connector block."""
    report = _lint(_connector_column() + _labeled_wire("W4 · WH FLRY-B 0.35", offset_x=180))
    assert not any(f.type == "label_on_connector" for f in report.findings)


@requires_drawio
def test_design_report_embeds_lint_advisory(tmp_path: Path) -> None:
    contract = HarnessContract.model_validate(example_contract_data())
    export_design(contract, tmp_path)
    gate_report = run_gates(contract, tmp_path)
    write_report(contract, gate_report, tmp_path)
    report = json.loads((tmp_path / "design-report.json").read_text(encoding="utf-8"))
    assert report["advisories"]["drawio_lint"]["verdict"] == "pass"
    md = (tmp_path / "design-report.md").read_text(encoding="utf-8")
    assert "## Diagram lint (advisory)" in md

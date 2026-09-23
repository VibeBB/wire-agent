"""harness-diagram.drawio.svg tests: valid SVG plus embedded drawio model."""

from __future__ import annotations

import base64
import urllib.parse
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

from helpers import example_contract_data
from wire.contract import HarnessContract
from wire.export import export_design

ARTIFACT = "harness-diagram.drawio.svg"


def _svg_root(out_dir: Path) -> ET.Element:
    return ET.parse(out_dir / ARTIFACT).getroot()


def _embedded_cells(out_dir: Path) -> dict[str, ET.Element]:
    """Decompress the root `content` attribute back into the drawio model."""
    content = _svg_root(out_dir).get("content")
    assert content is not None
    inflated = zlib.decompress(base64.b64decode(content), wbits=-15)
    xml_text = urllib.parse.unquote(inflated.decode("utf-8"))
    mxfile = ET.fromstring(xml_text)
    assert mxfile.tag == "mxfile"
    model = mxfile.find("diagram/mxGraphModel")
    assert model is not None
    cells: dict[str, ET.Element] = {}
    for cell in model.iter("mxCell"):
        cell_id = cell.get("id")
        if cell_id is not None:
            cells[cell_id] = cell
    return cells


def _export(tmp_path: Path) -> HarnessContract:
    contract = HarnessContract.model_validate(example_contract_data())
    export_design(contract, tmp_path)
    return contract


def test_drawio_svg_is_well_formed(tmp_path: Path) -> None:
    _export(tmp_path)
    root = _svg_root(tmp_path)
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    assert root.find("{http://www.w3.org/2000/svg}rect") is not None


def test_drawio_embedded_model_skeleton(tmp_path: Path) -> None:
    _export(tmp_path)
    cells = _embedded_cells(tmp_path)
    assert "0" in cells and "1" in cells
    assert cells["1"].get("parent") == "0"


def test_drawio_vertices_for_connectors_and_cavities(tmp_path: Path) -> None:
    contract = _export(tmp_path)
    cells = _embedded_cells(tmp_path)
    for connector in contract.connectors:
        conn = cells[f"conn-{connector.id}"]
        assert conn.get("vertex") == "1"
        assert conn.get("parent") == "1"
        for cavity in connector.cavities:
            cav = cells[f"cav-{connector.id}:{cavity.id}"]
            assert cav.get("vertex") == "1"
            assert cav.get("parent") == f"conn-{connector.id}"


def test_drawio_edges_bind_wire_endpoints(tmp_path: Path) -> None:
    contract = _export(tmp_path)
    cells = _embedded_cells(tmp_path)
    wire_edges = [cell for cell in cells.values() if cell.get("edge") == "1"]
    assert len(wire_edges) == len(contract.wires)
    for wire in contract.wires:
        edge = cells[f"wire-{wire.id}"]
        source = f"cav-{wire.from_endpoint.connector}:{wire.from_endpoint.cavity}"
        target = f"cav-{wire.to_endpoint.connector}:{wire.to_endpoint.cavity}"
        assert edge.get("source") == source
        assert edge.get("target") == target
        assert source in cells and target in cells
        value = edge.get("value") or ""
        assert wire.id in value and wire.net in value


def test_drawio_edge_color_follows_signal_class(tmp_path: Path) -> None:
    contract = _export(tmp_path)
    cells = _embedded_cells(tmp_path)
    nets = contract.net_map()
    for wire in contract.wires:
        style = cells[f"wire-{wire.id}"].get("style") or ""
        assert "strokeColor=" in style
        if nets[wire.net].signal_class == "power":
            assert "#c00000" in style

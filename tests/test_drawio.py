"""harness diagram tests: the mxfile model behind the drawio projection.

The rendered artifact is ``harness-diagram.drawio.svg``: drawio-desktop's own
render with the editable mxfile embedded in its ``content`` attribute. The
export fails closed when drawio is absent, so every test here requires the
wire-tools image's drawio-desktop + xvfb.
"""

from __future__ import annotations

import shutil
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from helpers import example_contract_data
from wire.contract import HarnessContract
from wire.export import export_design

DRAWIO_PRESENT = shutil.which("drawio") is not None and shutil.which("xvfb-run") is not None
pytestmark = pytest.mark.skipif(
    not DRAWIO_PRESENT,
    reason="export needs drawio-desktop + xvfb (both ship in the wire-tools image)",
)

ARTIFACT = "harness-diagram.drawio.svg"


def _mxfile(out_dir: Path) -> ET.Element:
    svg_path = out_dir / ARTIFACT
    content = ET.parse(svg_path).getroot().get("content")
    assert content is not None
    try:
        mxfile = ET.fromstring(content)
    except ET.ParseError:
        mxfile = ET.fromstring(urllib.parse.unquote(content))
    assert mxfile.tag == "mxfile"
    return mxfile


def _embedded_cells(out_dir: Path) -> dict[str, ET.Element]:
    model = _mxfile(out_dir).find("diagram/mxGraphModel")
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


def test_drawio_projection_written(tmp_path: Path) -> None:
    _export(tmp_path)
    rendered = tmp_path / ARTIFACT
    # drawio-desktop render: svg with the mxfile embedded in `content`.
    root = ET.parse(rendered).getroot()
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    assert "mxfile" in (root.get("content") or "")


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


def test_drawio_wire_labels_get_unique_offsets(tmp_path: Path) -> None:
    import copy

    data = copy.deepcopy(example_contract_data())
    for wid in ("W4", "W5"):
        wire = copy.deepcopy(data["wires"][0])
        wire["id"] = wid
        data["wires"].append(wire)
    contract = HarnessContract.model_validate(data)
    export_design(contract, tmp_path)
    cells = _embedded_cells(tmp_path)
    offsets: list[float] = []
    for wire in contract.wires:
        geometry = cells[f"wire-{wire.id}"].find("mxGeometry")
        assert geometry is not None
        offset = geometry.find("mxPoint")
        assert offset is not None and offset.get("as") == "offset"
        offsets.append(float(offset.get("y") or "0"))
    assert len(set(offsets)) == len(offsets)


def test_drawio_edge_color_prefers_physical_wire_color(tmp_path: Path) -> None:
    """Physical insulation color wins; signal class is only the fallback."""
    import copy

    data = copy.deepcopy(example_contract_data())
    data["wires"][0]["color"] = "RD"
    data["wires"][1]["color"] = None
    contract = HarnessContract.model_validate(data)
    export_design(contract, tmp_path)
    cells = _embedded_cells(tmp_path)
    nets = contract.net_map()
    style = cells[f"wire-{data['wires'][0]['id']}"].get("style") or ""
    assert "strokeColor=#d32f2f" in style  # RD insulation, not the class color
    for wire in contract.wires:
        style = cells[f"wire-{wire.id}"].get("style") or ""
        assert "strokeColor=" in style
        if wire.color is None and nets[wire.net].signal_class == "power":
            assert "#c00000" in style


def test_drawio_striped_wire_draws_second_color(tmp_path: Path) -> None:
    import copy

    data = copy.deepcopy(example_contract_data())
    data["wires"][0]["color"] = "RD/BK"
    contract = HarnessContract.model_validate(data)
    export_design(contract, tmp_path)
    cells = _embedded_cells(tmp_path)
    stripe = cells[f"wire-{data['wires'][0]['id']}-stripe"]
    assert stripe.get("edge") == "1"
    assert "strokeColor=#1a1a1a" in (stripe.get("style") or "")
    assert "dashed=1" in (stripe.get("style") or "")
    base = cells[f"wire-{data['wires'][0]['id']}"]
    assert "strokeColor=#d32f2f" in (base.get("style") or "")


def test_drawio_splice_vertex_and_leg_edges(tmp_path: Path) -> None:
    import copy

    data = copy.deepcopy(example_contract_data())
    data["splices"] = [{"id": "SP1", "kind": "crimp"}]
    data["wires"][0]["to_endpoint"] = {"splice": "SP1"}
    leg = copy.deepcopy(data["wires"][1])
    leg["id"] = "W9"
    leg["from_endpoint"] = {"splice": "SP1"}
    leg["to_endpoint"] = {"connector": "C2", "cavity": "4"}
    data["wires"].append(leg)
    contract = HarnessContract.model_validate(data)
    export_design(contract, tmp_path)
    cells = _embedded_cells(tmp_path)
    splice = cells["splice-SP1"]
    assert splice.get("vertex") == "1"
    wire0 = cells[f"wire-{data['wires'][0]['id']}"]
    assert wire0.get("target") == "splice-SP1"
    leg_edge = cells["wire-W9"]
    assert leg_edge.get("source") == "splice-SP1"
    assert leg_edge.get("target") == "cav-C2:4"
    assert "ellipse" in (splice.get("style") or "")


def test_drawio_loop_wire_bumps_off_inner_edge(tmp_path: Path) -> None:
    import copy

    data = copy.deepcopy(example_contract_data())
    loop_wire = copy.deepcopy(data["wires"][0])
    loop_wire["id"] = "W8"
    loop_wire["to_endpoint"] = {"connector": "C1", "cavity": "4"}
    data["wires"].append(loop_wire)
    contract = HarnessContract.model_validate(data)
    export_design(contract, tmp_path)
    cells = _embedded_cells(tmp_path)
    edge = cells["wire-W8"]
    style = edge.get("style") or ""
    # Same-connector loops hang a small bump off the channel-facing side.
    assert "exitX=1" in style and "entryX=1" in style


def test_drawio_unused_cavity_cells_dimmed(tmp_path: Path) -> None:
    contract = _export(tmp_path)
    cells = _embedded_cells(tmp_path)
    used = {
        (endpoint.connector, endpoint.cavity)
        for wire in contract.wires
        for endpoint in (wire.from_endpoint, wire.to_endpoint)
        if endpoint.connector is not None
    }
    for connector in contract.connectors:
        for cavity in connector.cavities:
            style = cells[f"cav-{connector.id}:{cavity.id}"].get("style") or ""
            if (connector.id, cavity.id) in used:
                assert "fillColor=#f5f5f5" not in style
            else:
                assert "fillColor=#f5f5f5" in style
                assert "fontColor=#9e9e9e" in style


def test_drawio_twisted_pair_band(tmp_path: Path) -> None:
    import copy

    data = copy.deepcopy(example_contract_data())
    data["nets"][0]["twisted_pair_with"] = data["nets"][1]["id"]
    contract = HarnessContract.model_validate(data)
    export_design(contract, tmp_path)
    cells = _embedded_cells(tmp_path)
    twist = [cell for cell in cells.values() if (cell.get("id") or "").startswith("twist-")]
    assert twist, "expected a twist band cell"
    value = twist[0].get("value") or ""
    assert "twisted pair" in value
    wire0 = cells[f"wire-{data['wires'][0]['id']}"]
    assert "TP" in (wire0.get("value") or "")

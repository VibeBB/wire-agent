# pyright: reportPrivateUsage=false
"""Drawing-frame tests: the ISO 5457 / JIS Z 8311 sheet frame and ISO 7200
title block emitted on the drawio model's bottom "frame" layer.

All checks run on the mxfile text — no drawio-desktop needed. Sizes are
drawio px (100 px/inch): A4 landscape is 297x210 mm = 1169x827 px.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from helpers import example_contract_data
from wire.contract import HarnessContract
from wire.export import (
    _BORDER_LEFT_MM,
    _BORDER_MM,
    _frame_geometry,
    _harness_mxfile,
    _mm,
    _zone_spans,
)

PX_A4 = (1169.0, 827.0)  # 297 x 210 mm rounded at 100 px/inch


def _contract() -> HarnessContract:
    return HarnessContract.model_validate(example_contract_data())


def _model() -> ET.Element:
    mxfile = ET.fromstring(_harness_mxfile(_contract()))
    model = mxfile.find("diagram/mxGraphModel")
    assert model is not None
    return model


def _cells(model: ET.Element) -> dict[str, ET.Element]:
    cells: dict[str, ET.Element] = {}
    for cell in model.iter("mxCell"):
        cell_id = cell.get("id")
        if cell_id is not None:
            cells[cell_id] = cell
    return cells


def _geo(cell: ET.Element) -> tuple[float, float, float, float]:
    g = cell.find("mxGeometry")
    assert g is not None
    return (
        float(g.get("x") or 0),
        float(g.get("y") or 0),
        float(g.get("width") or 0),
        float(g.get("height") or 0),
    )


def test_sheet_ladder_picks_smallest_that_fits() -> None:
    # content w/h in px; A4 landscape drawing space is ~1051x748 px.
    cases = [
        (900.0, 300.0, "A4"),
        (1200.0, 300.0, "A3"),
        (1700.0, 400.0, "A2"),
        (2400.0, 400.0, "A1"),
        (3500.0, 500.0, "A0"),
        (700.0, 5000.0, "A0x2"),
        (700.0, 8000.0, "A0x3"),
        (700.0, 12000.0, "210x3115"),  # custom: mm dims as designation
        (6000.0, 400.0, "1554x169"),  # wider than any sheet's drawing space
    ]
    for w, h, expected in cases:
        assert _frame_geometry(w, h)["name"] == expected, (w, h, expected)


@pytest.mark.parametrize(
    ("w_mm", "h_mm", "fields_w", "fields_h"),
    [
        (297, 210, 6, 4),  # A4
        (420, 297, 8, 6),  # A3
        (594, 420, 12, 8),  # A2
        (841, 594, 16, 12),  # A1
        (1189, 841, 24, 16),  # A0
    ],
)
def test_zone_field_counts_match_iso5457_table2(
    w_mm: int, h_mm: int, fields_w: int, fields_h: int
) -> None:
    # Field count per sheet edge: _zone_spans over the half dimension must
    # reproduce ISO 5457 Table 2 (fields measured from the symmetry axes).
    half_w_px = _mm(w_mm) / 2
    half_h_px = _mm(h_mm) / 2
    assert 2 * len(_zone_spans(half_w_px)) == fields_w
    assert 2 * len(_zone_spans(half_h_px)) == fields_h


def test_frame_geometry_margins_and_title_block() -> None:
    frame = _frame_geometry(900.0, 300.0)
    sw, sh = frame["w"], frame["h"]
    ds_x, ds_y, ds_w, ds_h = frame["ds"]
    assert (sw, sh) == pytest.approx(PX_A4, abs=1.0)
    assert ds_x == pytest.approx(_mm(_BORDER_LEFT_MM))
    assert ds_y == pytest.approx(_mm(_BORDER_MM))
    assert ds_w == pytest.approx(sw - _mm(_BORDER_LEFT_MM) - _mm(_BORDER_MM))
    assert ds_h == pytest.approx(sh - 2 * _mm(_BORDER_MM))
    tb_x, tb_y, tb_w, tb_h = frame["tb"]
    # Title block sits in the bottom-right corner of the drawing space.
    assert tb_x + tb_w == pytest.approx(sw - _mm(_BORDER_MM))
    assert tb_y + tb_h == pytest.approx(sh - _mm(_BORDER_MM))


def test_model_page_is_sheet_and_frame_layer_is_bottom() -> None:
    model = _model()
    assert float(model.get("pageWidth") or 0) == pytest.approx(PX_A4[0], abs=1.0)
    assert float(model.get("pageHeight") or 0) == pytest.approx(PX_A4[1], abs=1.0)
    root = model.find("root")
    assert root is not None
    layers = [c.get("id") for c in root if c.get("parent") == "0"]
    # Document order = z-order: frame first (bottom), wires last (top).
    assert layers == ["frame", "1", "wires"]


def test_frame_border_and_centring_marks() -> None:
    cells = _cells(_model())
    border = _geo(cells["frame-border"])
    assert border == pytest.approx((78.7402, 39.3701, 1050.89, 748.26), abs=0.01)
    sheet = _geo(cells["frame-sheet"])
    assert sheet == pytest.approx((0.0, 0.0, *PX_A4), abs=0.01)
    # Centring marks cross the border strip at each symmetry-axis end.
    cy = PX_A4[1] / 2
    lm = _geo(cells["frame-cmark-left"])
    assert lm[0] == 0.0 and lm[1] == pytest.approx(cy, abs=2.0)
    assert lm[2] == pytest.approx(_mm(_BORDER_LEFT_MM) + _mm(10.0), abs=0.05)
    rm = _geo(cells["frame-cmark-right"])
    assert rm[0] + rm[2] == pytest.approx(PX_A4[0], abs=0.01)


def test_frame_zone_ticks_and_labels() -> None:
    cells = _cells(_model())
    # A4 landscape: 6 fields wide (ticks at ±50 mm, ±100 mm of cx), 4 tall.
    top_ticks = [c for cid, c in cells.items() if (cid or "").startswith("frame-tick-t")]
    assert len(top_ticks) == 4
    xs = sorted(_geo(t)[0] + _geo(t)[2] / 2 for t in top_ticks)
    cx = PX_A4[0] / 2
    assert xs[0] == pytest.approx(cx - _mm(100.0), abs=0.5)
    assert xs[-1] == pytest.approx(cx + _mm(100.0), abs=0.5)
    top_labels = [cells[f"frame-lab-t{i}"].get("value") for i in range(6)]
    assert top_labels == ["1", "2", "3", "4", "5", "6"]
    left_labels = [cells[f"frame-lab-l{i}"].get("value") for i in range(4)]
    assert left_labels == ["A", "B", "C", "D"]
    # No tick may sit on the symmetry axis (the centring mark owns it).
    for x in xs:
        assert abs(x - cx) > _mm(1.0)


def test_frame_cells_stay_on_frame_layer() -> None:
    cells = _cells(_model())
    for cid, cell in cells.items():
        if cid.startswith(("frame-", "tb-")):
            assert cell.get("parent") == "frame", cid


def test_title_block_fields() -> None:
    contract = _contract()
    cells = _cells(_model())
    frame = _frame_geometry(880.0, 274.0)
    outer = _geo(cells["tb-outer"])
    assert outer[0] + outer[2] == pytest.approx(frame["w"] - _mm(_BORDER_MM), abs=0.01)
    values = [cells[f"tb-{r}{c}"].get("value") or "" for r in range(3) for c in range(4)]
    text = " ".join(values)
    assert contract.contract_id in text
    assert contract.revision in text
    assert "1/1" in text  # segment / total sheets
    assert "NTS" in text  # scale
    assert "A4" in text  # size designation
    # Deterministic artifacts have no wall-clock date — em dash placeholder.
    assert "Date of issue" in text and "—" in text


def test_size_designation_in_bottom_border() -> None:
    cells = _cells(_model())
    size = _geo(cells["frame-size"])
    assert cells["frame-size"].get("value") == "A4"
    assert size[1] == pytest.approx(PX_A4[1] - _mm(_BORDER_MM), abs=0.01)
    assert size[0] + size[2] < PX_A4[0]


def _doc_rows(cells: dict[str, ET.Element], block_id: str) -> list[str]:
    rows: list[str] = []
    i = 0
    while f"{block_id}-r{i}" in cells:
        rows.append(cells[f"{block_id}-r{i}"].get("value") or "")
        i += 1
    return rows


def test_doc_blocks_present_below_pin_table() -> None:
    cells = _cells(_model())
    for block_id in ("doc-legend", "doc-notes"):
        assert block_id in cells, block_id
        cell = cells[block_id]
        assert cell.get("parent") == "1"
        assert "swimlane" in (cell.get("style") or "")
        assert (cell.get("value") or "").strip()
        # The strip sits below the connector columns inside the frame.
        x, y, w, h = _geo(cell)
        fx, fy, fw, fh = _geo(cells["frame-border"])
        assert fx <= x and x + w <= fx + fw + 0.5
        assert fy <= y and y + h <= fy + fh + 0.5
        conn_bottom = max(
            _geo(c)[1] + _geo(c)[3] for cid, c in cells.items() if cid.startswith("conn-")
        )
        assert y > conn_bottom


def test_doc_legend_explains_markings() -> None:
    rows = _doc_rows(_cells(_model()), "doc-legend")
    assert rows
    text = " ".join(rows)
    for phrase in (
        "insulation color",
        "shielded",
        "unused cavity",
        "splice",
        "twisted-pair",
    ):
        assert phrase in text, phrase


def test_doc_notes_carry_manufacturing_context() -> None:
    contract = _contract()
    rows = _doc_rows(_cells(_model()), "doc-notes")
    text = " ".join(rows)
    assert f"IPC-A-620 cl.{contract.ipc_class}" in text
    assert f"{contract.ambient_temperature_c:g} °C" in text
    # Companion artifacts a no-context shop floor needs, named on the sheet.
    for artifact in ("wire-list.csv", "cut-table.csv", "bom.csv"):
        assert artifact in text, artifact
    # Route instructions: ids, protection, and worst-case bend radius.
    for route in contract.routes:
        assert route.id in text
    assert "bend>=12mm" in text and "bend>=10mm" in text
    # Service life and unused cavities (seal note).
    assert "30 mating" in text
    assert "cav. unused" in text


def test_doc_notes_cover_declared_features() -> None:
    import copy

    data = copy.deepcopy(example_contract_data())
    data["splices"] = [{"id": "SP1", "kind": "crimp"}]
    data["wires"][0]["to_endpoint"] = {"splice": "SP1"}
    data["nets"][0]["twisted_pair_with"] = data["nets"][1]["id"]
    data["nets"][2]["shield_required"] = True
    data["routes"][0]["flex_required"] = True
    data["routes"][0]["anchors"] = ["B1", "A2"]
    data["service"]["flex_cycles"] = 500
    contract = HarnessContract.model_validate(data)
    model = ET.fromstring(_harness_mxfile(contract)).find("diagram/mxGraphModel")
    assert model is not None
    text = " ".join(_doc_rows(_cells(model), "doc-notes"))
    assert "splice SP1 crimp" in text
    assert f"twisted {data['nets'][0]['id']}⇄{data['nets'][1]['id']}" in text
    assert f"net {data['nets'][2]['id']} shielded" in text
    assert "flex" in text and "anchors A2,B1" in text
    assert "500 flex" in text


def test_mxfile_is_deterministic_and_well_formed() -> None:
    a = _harness_mxfile(_contract())
    b = _harness_mxfile(_contract())
    assert a == b
    ET.fromstring(a)


def test_frame_cells_avoid_lint_checks() -> None:
    from wire.drawio_lint import lint_text

    report = lint_text(_harness_mxfile(_contract()), source=Path("d.drawio"))
    assert report.verdict == "pass"
    assert report.errors == 0

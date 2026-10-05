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
from pydantic import ValidationError

from helpers import example_contract_data
from wire.contract import HarnessContract, contract_sha256
from wire.diagram import (
    _CELL_PAD_PX,
    _MONO_ADVANCE,
    _TITLE_BLOCK_W_MM,
    _TITLE_FIELDS,
    _TITLE_ROW_MM,
)
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
        (700.0, 12000.0, "200x3121"),  # custom: mm dims as designation
        (6000.0, 400.0, "1544x175"),  # wider than any sheet's drawing space
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
    assert border == pytest.approx((39.3701, 39.3701, 1090.26, 748.26), abs=0.01)
    sheet = _geo(cells["frame-sheet"])
    assert sheet == pytest.approx((0.0, 0.0, *PX_A4), abs=0.01)
    # Centring marks span the border strip only: sheet edge to frame line,
    # never into the drawing space.
    cy = PX_A4[1] / 2
    bx, by, bw, bh = border
    lm = _geo(cells["frame-cmark-left"])
    assert lm[0] == 0.0 and lm[1] == pytest.approx(cy, abs=2.0)
    assert lm[0] + lm[2] == pytest.approx(bx, abs=0.01)
    rm = _geo(cells["frame-cmark-right"])
    assert rm[0] == pytest.approx(bx + bw, abs=0.01)
    assert rm[0] + rm[2] == pytest.approx(PX_A4[0], abs=0.01)
    tm = _geo(cells["frame-cmark-top"])
    assert tm[1] == 0.0 and tm[1] + tm[3] == pytest.approx(by, abs=0.01)
    bm = _geo(cells["frame-cmark-bottom"])
    assert bm[1] == pytest.approx(by + bh, abs=0.01)
    assert bm[1] + bm[3] == pytest.approx(PX_A4[1], abs=0.01)


def test_left_and_right_border_strips_match() -> None:
    cells = _cells(_model())
    left = [_geo(c) for cid, c in cells.items() if cid.startswith("frame-lab-l")]
    right = [_geo(c) for cid, c in cells.items() if cid.startswith("frame-lab-r")]
    assert left and len(left) == len(right)
    for geo in left + right:
        assert geo[2] == pytest.approx(_mm(_BORDER_MM))
    assert _mm(_BORDER_LEFT_MM) == pytest.approx(_mm(_BORDER_MM))


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


def _title_values(cells: dict[str, ET.Element]) -> dict[str, str]:
    labels = {
        cid.removesuffix("-lab"): cell.get("value") or ""
        for cid, cell in cells.items()
        if cid.startswith("tb-") and cid.endswith("-lab")
    }
    return {label: cells[f"{cid}-val"].get("value") or "" for cid, label in labels.items()}


def _model_for(contract: HarnessContract) -> dict[str, ET.Element]:
    mxfile = ET.fromstring(_harness_mxfile(contract))
    model = mxfile.find("diagram/mxGraphModel")
    assert model is not None
    return _cells(model)


def test_title_block_fields() -> None:
    contract = _contract()
    value = _title_values(_cells(_model()))
    assert value["Identification number"] == contract.contract_id
    assert value["Title, Supplementary title"] == contract.name
    assert value["Rev."] == contract.revision
    assert value["Sheet"] == "1/1"
    assert value["Scale"] == "NTS"
    assert value["Legal owner"] == "VibeBB"
    assert value["Lang."] == "en"
    assert value["Workmanship"] == "IPC/WHMA-A-620 Class 2"
    assert value["Units"] == "m, mm (note 3)"
    assert value["Document type"] == "Harness connection diagram"
    assert value["Created by"].startswith("wire-agent/")
    # Unset people and dates are an em dash, and the status says why.
    assert value["Approved by"] == "—"
    assert value["Date of issue"] == "—"
    assert value["Document status"] == "In preparation"
    # The sheet size lives in the frame's size designation, not here.
    assert "Size" not in value and "A4" not in value.values()
    assert set(value) == {label for _k, label, *_rest in _TITLE_FIELDS}


def test_frame_layer_is_locked() -> None:
    cells = _cells(_model())
    assert "locked=1" in (cells["frame"].get("style") or "")
    assert "locked=1" not in (cells["1"].get("style") or "")


def test_title_block_classification() -> None:
    data = example_contract_data()
    data["drawing"]["classification"] = "harness, sensor"
    value = _title_values(_model_for(HarnessContract.model_validate(data)))
    assert value["Classification/key words"] == "harness, sensor"
    assert _title_values(_cells(_model()))["Classification/key words"] == "—"


def test_title_block_binds_the_contract_digest() -> None:
    contract = _contract()
    value = _title_values(_cells(_model()))
    assert contract_sha256(contract).startswith(value["Contract sha256"])
    assert len(value["Contract sha256"]) == 16


def test_title_block_supplementary_title() -> None:
    contract = _contract()
    cells = _cells(_model())
    assert cells["tb-title-sup"].get("value") == contract.drawing.supplementary_title
    data = example_contract_data()
    del data["drawing"]["supplementary_title"]
    derived = _model_for(HarnessContract.model_validate(data))
    assert derived["tb-title-sup"].get("value") == "3 wires · 2 connectors · 2 routes"


def test_title_block_arrangement() -> None:
    cells = _cells(_model())
    frame = _frame_geometry(880.0, 274.0)
    outer = _geo(cells["tb-outer"])
    assert outer[0] + outer[2] == pytest.approx(frame["w"] - _mm(_BORDER_MM), abs=0.01)
    assert outer[2] == pytest.approx(_mm(_TITLE_BLOCK_W_MM), abs=0.01)
    right, bottom = outer[0] + outer[2], outer[1] + outer[3]
    boxes = {key: _geo(cells[f"tb-{key}"]) for key, *_rest in _TITLE_FIELDS}
    # The cells tile the block exactly: no gaps, no overlaps.
    assert sum(w * h for _x, _y, w, h in boxes.values()) == pytest.approx(
        outer[2] * outer[3], rel=1e-4
    )
    items = list(boxes.items())
    for i, (a, (ax, ay, aw, ah)) in enumerate(items):
        assert ax >= outer[0] - 0.01 and ax + aw <= right + 0.01, a
        assert ay >= outer[1] - 0.01 and ay + ah <= bottom + 0.01, a
        for b, (bx, by, bw, bh) in items[i + 1 :]:
            overlap_w = min(ax + aw, bx + bw) - max(ax, bx)
            overlap_h = min(ay + ah, by + bh) - max(ay, by)
            assert overlap_w <= 0.01 or overlap_h <= 0.01, (a, b)
    # Sheet number owns the bottom-right corner; the identification row
    # (rev, date of issue, language, sheet) runs along the bottom edge.
    sx, sy, sw_, sh_ = boxes["sheet"]
    assert sx + sw_ == pytest.approx(right, abs=0.01)
    assert sy + sh_ == pytest.approx(bottom, abs=0.01)
    for key in ("rev", "issued", "lang"):
        assert boxes[key][1] + boxes[key][3] == pytest.approx(bottom, abs=0.01)
    number = boxes["number"]
    assert number[0] + number[2] == pytest.approx(right, abs=0.01)
    assert number[1] + number[3] == pytest.approx(boxes["sheet"][1], abs=0.01)
    # Legal owner runs down the left edge through the lower three rows.
    owner = boxes["owner"]
    assert owner[0] == pytest.approx(outer[0], abs=0.01)
    assert owner[1] + owner[3] == pytest.approx(bottom, abs=0.01)
    assert owner[3] == pytest.approx(3 * _mm(_TITLE_ROW_MM), abs=0.01)
    # Technical data strip is the top row, above the administrative row.
    for key in ("workmanship", "units", "scale", "contract"):
        assert boxes[key][1] == pytest.approx(outer[1], abs=0.01)
    assert boxes["creator"][1] == pytest.approx(outer[1] + _mm(_TITLE_ROW_MM), abs=0.01)


@pytest.mark.parametrize(
    ("drawing", "status"),
    [
        ({}, "In preparation"),
        ({"approved_by": "J. Smith"}, "In approval"),
        ({"approved_by": "J. Smith", "date_of_issue": "2026-10-05"}, "Released"),
    ],
)
def test_title_block_document_status(drawing: dict[str, str], status: str) -> None:
    data = example_contract_data()
    data["drawing"] = {"legal_owner": "Acme", "created_by": "A. Author", **drawing}
    value = _title_values(_model_for(HarnessContract.model_validate(data)))
    assert value["Document status"] == status
    assert value["Approved by"] == drawing.get("approved_by", "—")
    assert value["Date of issue"] == drawing.get("date_of_issue", "—")
    assert value["Created by"] == "A. Author"
    assert value["Legal owner"] == "Acme"


@pytest.mark.parametrize(
    "drawing",
    [
        {"date_of_issue": "2026-10-05"},
        {"approved_by": "J. Smith", "date_of_issue": "2026-02-30"},
        {"language": "English"},
        {"legal_owner": ""},
        {"status": "Released"},
    ],
)
def test_drawing_info_rejects_unreleasable_metadata(drawing: dict[str, str]) -> None:
    data = example_contract_data()
    data["drawing"] = drawing
    with pytest.raises(ValidationError):
        HarnessContract.model_validate(data)


def test_title_block_values_never_spill_over_cell_rules() -> None:
    data = example_contract_data()
    data["name"] = "rear-left-door-harness-with-window-lift-and-mirror-fold"
    data["revision"] = "rev-AB-2026-candidate"
    cells = _model_for(HarnessContract.model_validate(data))
    for key, *_rest in _TITLE_FIELDS:
        val = cells[f"tb-{key}-val"]
        text = val.get("value") or ""
        size = float(
            dict(item.split("=", 1) for item in (val.get("style") or "").split(";") if "=" in item)[
                "fontSize"
            ]
        )
        width = _geo(cells[f"tb-{key}"])[2]
        assert len(text) * _MONO_ADVANCE * size <= width - _CELL_PAD_PX + 0.01, key
    assert cells["tb-title-val"].get("value") == data["name"]
    assert cells["tb-rev-val"].get("value", "").endswith("…")


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
    assert f"IPC/WHMA-A-620 class {contract.ipc_class}" in text
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
    assert "flex" in text and "anchors B1 > A2" in text
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

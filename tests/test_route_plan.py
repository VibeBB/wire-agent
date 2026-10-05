# pyright: reportPrivateUsage=false
"""Route plan projection and report vision points."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from helpers import REPO_ROOT, example_contract_data
from wire.contract import HarnessContract
from wire.export import export_design
from wire.gates import run_gates
from wire.imports import import_envelope, load_envelope_source
from wire.report import vision_points, write_report
from wire.route_plan import ROUTE_PLAN_NAME, ROUTE_PLAN_PNG, route_plan_mxfile

ENVELOPE = REPO_ROOT / "examples" / "sensor-harness" / "sensor-harness.mech-envelope.json"
DRAWIO_PRESENT = shutil.which("drawio") is not None and shutil.which("xvfb-run") is not None


def routed_contract() -> HarnessContract:
    contract = HarnessContract.model_validate(example_contract_data())
    merged = import_envelope(contract, load_envelope_source(ENVELOPE), ENVELOPE)
    data = merged.model_dump(mode="json")
    data["routes"][0]["anchors"] = ["ctrl-exit", "lid-clip", "sensor-breakout"]
    data["routes"][1]["anchors"] = ["ctrl-exit", "motor-clip"]
    return HarnessContract.model_validate(data)


def test_no_route_plan_without_positions() -> None:
    assert route_plan_mxfile(HarnessContract.model_validate(example_contract_data())) is None


def test_route_plan_draws_anchors_and_routes() -> None:
    contract = routed_contract()
    mxfile = route_plan_mxfile(contract)
    assert mxfile is not None
    assert mxfile == route_plan_mxfile(contract)
    for name in ("ctrl-exit", "lid-clip", "sensor-breakout", "motor-clip"):
        assert f'id="anchor-{name}"' in mxfile
    assert 'source="anchor-ctrl-exit" target="anchor-lid-clip"' in mxfile
    assert 'source="anchor-lid-clip" target="anchor-sensor-breakout"' in mxfile
    assert "RT1: ctrl-exit &gt; lid-clip &gt; sensor-breakout | length 500 mm" in mxfile
    assert "anchor span 351 mm OK" in mxfile
    assert "shape=doubleEllipse" in mxfile  # grommet
    assert "rhombus" in mxfile  # breakout


def test_route_plan_flags_short_route() -> None:
    data = routed_contract().model_dump(mode="json")
    for segment in data["routes"][0]["segments"]:
        segment["length_m"] = 0.1
    contract = HarnessContract.model_validate(data)
    assert "TOO SHORT" in (route_plan_mxfile(contract) or "")
    statuses = {c.subject: c.status for c in run_gates(contract).checks if c.id == "route_geometry"}
    assert statuses["RT1"] == "fail"
    assert statuses["RT2"] == "pass"


def test_vision_points_lists_rendered_rasters(tmp_path: Path) -> None:
    assert vision_points(tmp_path) == []
    (tmp_path / "harness-diagram.png").write_bytes(b"\x89PNG")
    (tmp_path / ROUTE_PLAN_PNG).write_bytes(b"\x89PNG")
    assert vision_points(tmp_path) == [
        {"image": "harness-diagram.png", "checklist": "harness_diagram"},
        {"image": ROUTE_PLAN_PNG, "checklist": "route_plan"},
    ]


@pytest.mark.skipif(not DRAWIO_PRESENT, reason="needs drawio-desktop + xvfb (wire-tools image)")
def test_export_renders_route_plan(tmp_path: Path) -> None:
    contract = routed_contract()
    manifest = export_design(contract, tmp_path, png=True)
    paths = {f["path"] for f in manifest["files"]}
    assert {ROUTE_PLAN_NAME, ROUTE_PLAN_PNG} <= paths
    assert (tmp_path / ROUTE_PLAN_PNG).read_bytes().startswith(b"\x89PNG")
    gate_report = run_gates(contract, tmp_path)
    assert gate_report.verdict == "pass"
    report = write_report(contract, gate_report, tmp_path)
    assert "route-plan.png" in report.read_text(encoding="utf-8")

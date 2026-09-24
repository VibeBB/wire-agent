"""Export determinism, manifest, and provenance tests."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from pytest import TempPathFactory

from helpers import example_contract_data
from wire.contract import HarnessContract, contract_sha256
from wire.export import export_design
from wire.gates import run_gates
from wire.report import write_report

DRAWIO_PRESENT = shutil.which("drawio") is not None and shutil.which("xvfb-run") is not None
DIAGRAM_ARTIFACT = "harness-diagram.drawio.svg" if DRAWIO_PRESENT else "harness-diagram.drawio"
EXPECTED_ARTIFACTS = {
    "bom.csv",
    "bom.json",
    "cut-table.csv",
    DIAGRAM_ARTIFACT,
    "harness-diagram.drawio_lint.json",
    "manifest.json",
    "provenance.json",
    "wire-list.csv",
}


def _export(tmp_path: Path) -> tuple[HarnessContract, Path]:
    contract = HarnessContract.model_validate(example_contract_data())
    export_design(contract, tmp_path)
    return contract, tmp_path


def _hashes(out_dir: Path) -> dict[str, str]:
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out_dir.iterdir() if p.is_file()
    }


def test_export_writes_expected_artifacts(tmp_path: Path) -> None:
    _, out = _export(tmp_path)
    assert {p.name for p in out.iterdir()} == EXPECTED_ARTIFACTS


def test_export_is_deterministic(tmp_path: Path, tmp_path_factory: TempPathFactory) -> None:
    other = tmp_path_factory.mktemp("other")
    _export(tmp_path)
    _export(other)
    assert _hashes(tmp_path) == _hashes(other)


def test_manifest_records_artifact_shas(tmp_path: Path) -> None:
    contract, out = _export(tmp_path)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["contract_sha256"] == contract_sha256(contract)
    names = {f["path"] for f in manifest["files"]}
    assert names == EXPECTED_ARTIFACTS - {"manifest.json"}
    assert "manifest.json" not in names  # never lists itself
    for artifact in manifest["files"]:
        digest = hashlib.sha256((out / artifact["path"]).read_bytes()).hexdigest()
        assert artifact["sha256"] == digest


def test_provenance_records_contract_and_sources(tmp_path: Path) -> None:
    contract, out = _export(tmp_path)
    provenance = json.loads((out / "provenance.json").read_text(encoding="utf-8"))
    assert provenance["contract_sha256"] == contract_sha256(contract)
    assert provenance["contract_id"] == "WH-0001"
    assert provenance["schema_version"] == 1


def test_report_written(tmp_path: Path) -> None:
    contract, out = _export(tmp_path)
    report = run_gates(contract, out)
    write_report(contract, report, out)
    doc = json.loads((out / "design-report.json").read_text(encoding="utf-8"))
    assert doc["verdict"] == "pass"
    assert (
        (out / "design-report.md").read_text(encoding="utf-8").startswith("# Harness design report")
    )


def test_corrupted_artifact_fails_manifest(tmp_path: Path) -> None:
    contract, out = _export(tmp_path)
    (out / "wire-list.csv").write_text("tampered\n", encoding="utf-8")
    report = run_gates(contract, out)
    manifest = [c for c in report.checks if c.id == "manifest_integrity"]
    assert manifest and all(c.status == "fail" for c in manifest)
    assert report.verdict == "fail"


def test_cut_table_groups_identical_wires(tmp_path: Path) -> None:
    _, out = _export(tmp_path)
    rows = (out / "cut-table.csv").read_text(encoding="utf-8").splitlines()
    assert rows[0].startswith("wire_type,")
    assert len(rows) == 3  # header + 2 groups


def test_bom_counts_wire_terminations(tmp_path: Path) -> None:
    """BOM terminals count actual wire ends, not declared cavities —
    spare connector positions must not inflate purchasing quantities."""
    _, out = _export(tmp_path)
    bom = json.loads((out / "bom.json").read_text(encoding="utf-8"))
    terminals = {entry["terminal"]: entry["quantity"] for entry in bom["terminals"]}
    assert terminals == {"SXH-001T-P0.6": 6}  # 3 wires x 2 ends; pin 4 spare on both sides


def test_bom_falls_back_to_cavity_terminal(tmp_path: Path) -> None:
    """A connector endpoint without an explicit wire terminal uses the
    cavity's declared terminal series."""
    data = example_contract_data()
    for wire in data["wires"]:
        wire.pop("terminal_a", None)
        wire.pop("terminal_b", None)
    contract = HarnessContract.model_validate(data)
    export_design(contract, tmp_path)
    bom = json.loads((tmp_path / "bom.json").read_text(encoding="utf-8"))
    terminals = {entry["terminal"]: entry["quantity"] for entry in bom["terminals"]}
    assert terminals == {"SXH-001T-P0.6": 6}


def test_export_drawio_renders(tmp_path: Path, tmp_path_factory: TempPathFactory) -> None:
    """--png/--drawio add drawio-desktop renders; drawio/font versions may
    shift their bytes across hosts, so the manifest records actual hashes."""
    if not DRAWIO_PRESENT:
        pytest.skip("drawio-desktop/xvfb not installed")
    contract = HarnessContract.model_validate(example_contract_data())
    manifest = export_design(contract, tmp_path, png=True, drawio=["pdf", "xml"])
    png = tmp_path / "harness-diagram.png"
    assert png.read_bytes().startswith(b"\x89PNG")
    assert (tmp_path / "harness-diagram.pdf").read_bytes().startswith(b"%PDF")
    assert (tmp_path / "harness-diagram.drawio").read_text(encoding="utf-8").startswith("<mxfile")
    expected = EXPECTED_ARTIFACTS - {"manifest.json"} | {
        "harness-diagram.png",
        "harness-diagram.pdf",
        "harness-diagram.drawio",
    }
    assert {f["path"] for f in manifest["files"]} == expected
    entry = next(f for f in manifest["files"] if f["path"] == "harness-diagram.png")
    assert entry["sha256"] == hashlib.sha256(png.read_bytes()).hexdigest()
    # Same host, same drawio: repeated exports stay byte-identical.
    other = tmp_path_factory.mktemp("other")
    export_design(contract, other, png=True, drawio=["pdf", "xml"])
    assert (other / "harness-diagram.png").read_bytes() == png.read_bytes()


def test_export_drawio_render_requires_drawio(tmp_path: Path) -> None:
    """Without drawio-desktop the --png/--drawio renders fail closed."""
    if DRAWIO_PRESENT:
        pytest.skip("drawio-desktop present")
    contract = HarnessContract.model_validate(example_contract_data())
    with pytest.raises(RuntimeError):
        export_design(contract, tmp_path, png=True)

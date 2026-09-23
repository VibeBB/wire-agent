"""Export determinism, manifest, and provenance tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pytest import TempPathFactory

from helpers import example_contract_data
from wire.contract import HarnessContract, contract_sha256
from wire.export import export_design
from wire.gates import run_gates
from wire.report import write_report

EXPECTED_ARTIFACTS = {
    "bom.csv",
    "bom.json",
    "cut-table.csv",
    "harness-diagram.drawio.svg",
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


def test_harness_diagram_wire_labels_do_not_overlap(tmp_path: Path) -> None:
    import copy
    import re

    data = copy.deepcopy(example_contract_data())
    # Parallel wires on one connector pair already collide; add mirrored
    # connectors and two crossing wires whose midpoints coincide, so the
    # label staggering is exercised on both collision modes.
    c3 = copy.deepcopy(data["connectors"][0])
    c3["id"] = "C3"
    c4 = copy.deepcopy(data["connectors"][1])
    c4["id"] = "C4"
    data["connectors"].extend([c3, c4])
    for wid, a, b in (("W4", "C1", "C4"), ("W5", "C3", "C2")):
        wire = copy.deepcopy(data["wires"][0])
        wire["id"] = wid
        wire["from_endpoint"]["connector"] = a
        wire["to_endpoint"]["connector"] = b
        data["wires"].append(wire)
    contract = HarnessContract.model_validate(data)
    export_design(contract, tmp_path)
    svg = (tmp_path / "harness-diagram.svg").read_text(encoding="utf-8")
    anchors = re.findall(r'<text x="([\d.]+)" y="([\d.]+)" fill="#225">', svg)
    assert len(anchors) == len(data["wires"])
    assert len(set(anchors)) == len(anchors)

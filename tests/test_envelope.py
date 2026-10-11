# pyright: reportPrivateUsage=false
"""Interchange envelope v3: producer sidecars and the import_provenance gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from test_gate_boundaries import _checks, _report, example_contract_data
from test_records import _decision
from wire import _envelope, records
from wire.cli import cmd_crimp

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/sensor-harness"


def _produce(root: Path) -> tuple[Path, Path, str]:
    source = root / "harness.contract.json"
    source.write_text('{"contract": 1}\n', encoding="utf-8")
    event_id = records.record_decision(_decision("harness.contract.json"), root)["record"][
        "event_id"
    ]
    artifact = root / "H1.wire-crimp.json"
    artifact.write_text('{"rows": []}\n', encoding="utf-8")
    return source, artifact, str(event_id)


def test_sidecar_cites_decisions_and_checks_pass(tmp_path: Path) -> None:
    source, artifact, event_id = _produce(tmp_path)
    body = _envelope.write_envelope(artifact, "wire", [source], tmp_path)
    assert body["decision_refs"] == [event_id]
    assert body["sources"] == [
        {"path": "harness.contract.json", "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
    ]
    side = tmp_path / "H1.wire-crimp.provenance.json"
    assert json.loads(side.read_text(encoding="utf-8"))["envelope_version"] == 3
    assert _envelope.check_envelope(artifact, "wire", tmp_path)[0] == "pass"


def test_uncited_source_has_no_decision_refs(tmp_path: Path) -> None:
    _, artifact, _ = _produce(tmp_path)
    other = tmp_path / "other.json"
    other.write_text("{}\n", encoding="utf-8")
    assert _envelope.write_envelope(artifact, "wire", [other], tmp_path)["decision_refs"] == []


@pytest.mark.parametrize(
    ("corrupt", "status", "needle"),
    [
        ("drop-sidecar", "unknown", "no envelope v3"),
        ("garble-sidecar", "fail", "malformed"),
        ("edit-artifact", "fail", "other artifact"),
        ("edit-source", "fail", "source changed"),
        ("drop-source", "unknown", "source unreadable"),
    ],
)
def test_corrupted_provenance_does_not_pass(
    tmp_path: Path, corrupt: str, status: str, needle: str
) -> None:
    source, artifact, _ = _produce(tmp_path)
    _envelope.write_envelope(artifact, "wire", [source], tmp_path)
    side = _envelope.sidecar_path(artifact)
    if corrupt == "drop-sidecar":
        side.unlink()
    elif corrupt == "garble-sidecar":
        side.write_text("[", encoding="utf-8")
    elif corrupt == "edit-artifact":
        artifact.write_text("{}\n", encoding="utf-8")
    elif corrupt == "edit-source":
        source.write_text("{}\n", encoding="utf-8")
    else:
        source.unlink()
    result, detail = _envelope.check_envelope(artifact, "wire", tmp_path)
    assert result == status
    assert needle in detail


def test_sidecar_fields_and_decision_log_fail_closed(tmp_path: Path) -> None:
    source, artifact, _ = _produce(tmp_path)
    _envelope.write_envelope(artifact, "wire", [source], tmp_path)
    side = _envelope.sidecar_path(artifact)
    good = json.loads(side.read_text(encoding="utf-8"))

    assert _envelope.check_envelope(artifact, "mech", tmp_path)[0] == "fail"
    pinned = hashlib.sha256(b"other").hexdigest()
    assert _envelope.check_envelope(artifact, "wire", tmp_path, pinned)[0] == "fail"

    side.write_text(json.dumps(good | {"envelope_version": 2}), encoding="utf-8")
    assert _envelope.check_envelope(artifact, "wire", tmp_path)[0] == "fail"
    side.write_text(json.dumps(good | {"decision_refs": ["vrp-forged"]}), encoding="utf-8")
    status, detail = _envelope.check_envelope(artifact, "wire", tmp_path)
    assert (status, "vrp-forged" in detail) == ("fail", True)

    side.write_text(json.dumps(good), encoding="utf-8")
    log = tmp_path / "observations/wire/decisions.jsonl"
    log.write_text(log.read_text(encoding="utf-8").replace("far-edge", "same-bundle"), "utf-8")
    status, detail = _envelope.check_envelope(artifact, "wire", tmp_path)
    assert (status, "integrity" in detail) == ("fail", True)
    with pytest.raises(ValueError, match="integrity"):
        _envelope.write_envelope(artifact, "wire", [source], tmp_path)

    log.unlink()
    assert _envelope.check_envelope(artifact, "wire", tmp_path)[0] == "unknown"


def test_import_provenance_gate_on_mech_imports(tmp_path: Path) -> None:
    blob = tmp_path / "housing.envelope.json"
    blob.write_text('{"system": "mech"}\n', encoding="utf-8")
    digest = hashlib.sha256(blob.read_bytes()).hexdigest()
    data = example_contract_data()
    data["imported_sources"] = [{"id": "I1", "system": "mech", "ref": str(blob), "sha256": digest}]
    assert _checks(_report(data), "import_provenance")[0].status == "unknown"

    _envelope.write_envelope(blob, "mech", [], tmp_path)
    assert _checks(_report(data), "import_provenance")[0].status == "pass"

    data["imported_sources"][0]["sha256"] = hashlib.sha256(b"x").hexdigest()
    assert _checks(_report(data), "import_provenance")[0].status == "fail"

    data["imported_sources"] = []
    check = _checks(_report(data), "import_provenance")[0]
    assert (check.status, check.detail) == ("pass", "no mech imports")


def test_crimp_export_writes_the_sidecar(tmp_path: Path) -> None:
    contract = tmp_path / "sensor-harness.contract.json"
    shutil.copy(EXAMPLE / contract.name, contract)
    result = cmd_crimp(argparse.Namespace(contract=str(contract), out=str(tmp_path / "out")))
    artifact = Path(result["path"])
    assert result["decision_refs"] == []
    assert _envelope.sidecar_path(artifact).is_file()
    assert _envelope.check_envelope(artifact, "wire", tmp_path)[0] == "pass"

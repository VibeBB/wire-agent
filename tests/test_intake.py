"""Intake gate tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from helpers import example_contract_data, example_intake_data
from wire.contract import HarnessContract
from wire.intake import Intake, IntakeReport, OpenQuestion, check_intake

CP = Path("c.contract.json")
IP = Path("c.intake.json")


def _check(
    contract_data: dict[str, Any] | None = None,
    intake_data: dict[str, Any] | None = None,
) -> IntakeReport:
    contract = HarnessContract.model_validate(
        contract_data if contract_data is not None else example_contract_data()
    )
    intake = Intake.model_validate(
        intake_data if intake_data is not None else example_intake_data()
    )
    return check_intake(contract, intake, CP, IP)


def test_example_intake_ready() -> None:
    report = _check()
    assert report.verdict == "ready"
    assert report.reasons == []
    assert report.sha_matches is True


def test_sha_mismatch_blocks() -> None:
    data = example_intake_data()
    data["contract_sha256"] = "0" * 64
    report = _check(intake_data=data)
    assert report.verdict == "blocked"
    assert report.sha_matches is False
    assert any("sha256" in r for r in report.reasons)


def test_unmapped_element_blocks() -> None:
    data = example_intake_data()
    data["element_sources"].pop("W1")
    report = _check(intake_data=data)
    assert report.verdict == "blocked"
    assert "W1" in report.unmapped_elements


def test_unknown_source_id_blocks() -> None:
    data = example_intake_data()
    data["element_sources"]["W1"].append("R99")
    report = _check(intake_data=data)
    assert report.verdict == "blocked"
    assert report.unknown_sources.get("element_sources.W1") == ["R99"]


def test_unknown_element_blocks() -> None:
    data = example_intake_data()
    data["element_sources"]["W99"] = ["R1"]
    report = _check(intake_data=data)
    assert report.verdict == "blocked"
    assert "W99" in report.unknown_elements


def test_assumption_only_element_blocks() -> None:
    data = example_intake_data()
    data["element_sources"]["W1"] = ["A1"]
    report = _check(intake_data=data)
    assert report.verdict == "blocked"
    assert "W1" in report.assumption_only_elements


def test_open_question_blocks() -> None:
    data = example_intake_data()
    data["open_questions"] = [{"id": "Q1", "text": "Is the ambient rating 60 or 85 C?"}]
    report = _check(intake_data=data)
    assert report.verdict == "blocked"
    assert report.open_questions == [
        OpenQuestion(id="Q1", text="Is the ambient rating 60 or 85 C?")
    ]


def test_intake_file_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "x.intake.json"
    path.write_text(json.dumps(example_intake_data()), encoding="utf-8")
    intake = Intake.model_validate(json.loads(path.read_text(encoding="utf-8")))
    contract = HarnessContract.model_validate(example_contract_data())
    assert check_intake(contract, intake, CP, path).verdict == "ready"


def _evidence_intake(tmp_path: Path) -> tuple[Intake, Path]:
    payload = b"pretend photo"
    image = tmp_path / "attachments" / "abcd1234abcd.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(payload)
    data = example_intake_data()
    data["assumptions"][0]["evidence"] = {
        "kind": "image",
        "path": str(image.relative_to(tmp_path)),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "note": "connector photo from the user",
    }
    intake = Intake.model_validate(data)
    return intake, tmp_path / "c.intake.json"


def test_evidence_ref_valid_passes(tmp_path: Path) -> None:
    intake, intake_path = _evidence_intake(tmp_path)
    contract = HarnessContract.model_validate(example_contract_data())
    report = check_intake(contract, intake, CP, intake_path)
    assert report.verdict == "ready"
    assert report.evidence_errors == []


def test_evidence_missing_file_blocks(tmp_path: Path) -> None:
    intake, intake_path = _evidence_intake(tmp_path)
    (tmp_path / "attachments" / "abcd1234abcd.png").unlink()
    contract = HarnessContract.model_validate(example_contract_data())
    report = check_intake(contract, intake, CP, intake_path)
    assert report.verdict == "blocked"
    assert report.evidence_errors == [
        f"{intake.assumptions[0].id} evidence attachments/abcd1234abcd.png: file missing"
    ]


def test_evidence_sha_mismatch_blocks(tmp_path: Path) -> None:
    intake, intake_path = _evidence_intake(tmp_path)
    (tmp_path / "attachments" / "abcd1234abcd.png").write_bytes(b"tampered")
    contract = HarnessContract.model_validate(example_contract_data())
    report = check_intake(contract, intake, CP, intake_path)
    assert report.verdict == "blocked"
    assert report.evidence_errors == [
        f"{intake.assumptions[0].id} evidence attachments/abcd1234abcd.png: sha256 mismatch"
    ]

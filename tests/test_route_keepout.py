"""route_keepout: anchor polylines against mech envelope keep-out volumes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from helpers import example_contract_data
from wire.contract import HarnessContract, contract_sha256
from wire.gates import GateCheck, run_gates
from wire.imports import EnvelopeSource, import_envelope

BOARD = {"name": "board", "min_mm": [100.0, -50.0, 0.0], "max_mm": [200.0, 50.0, 20.0]}


def _data(keepouts: list[dict[str, Any]] | None, z: float = 10.0) -> dict[str, Any]:
    data = example_contract_data()
    data["routes"][0]["anchors"] = ["A1", "A2"]
    source: dict[str, Any] = {
        "id": "I1",
        "system": "mech",
        "ref": "x.json",
        "anchors": ["A1", "A2"],
        "anchor_points": [
            {"name": "A1", "position_mm": [0.0, 0.0, z]},
            {"name": "A2", "position_mm": [300.0, 0.0, z]},
        ],
    }
    if keepouts is not None:
        source["keepouts"] = keepouts
    data["imported_sources"] = [source]
    return data


def _check(data: dict[str, Any]) -> GateCheck:
    report = run_gates(HarnessContract.model_validate(data))
    return next(check for check in report.checks if check.id == "route_keepout")


def test_route_through_a_keepout_fails() -> None:
    check = _check(_data([BOARD]))
    assert check.status == "fail"
    assert check.detail == "A1->A2 enters board"


@pytest.mark.parametrize(("z", "status"), [(19.999, "fail"), (20.0, "pass"), (20.001, "pass")])
def test_touching_the_keepout_face_passes(z: float, status: str) -> None:
    assert _check(_data([BOARD], z=z)).status == status


def test_extra_anchor_bends_the_route_around() -> None:
    data = _data([BOARD])
    data["routes"][0]["anchors"] = ["A1", "A3", "A2"]
    source = data["imported_sources"][0]
    source["anchors"].append("A3")
    source["anchor_points"].append({"name": "A3", "position_mm": [150.0, 0.0, 30.0]})
    data["routes"][0]["segments"][0]["length_m"] = 1.0
    check = _check(data)
    assert check.status == "pass"
    assert check.detail == "clear of 1 keep-outs"


def test_legacy_envelope_without_keepouts_is_unknown() -> None:
    check = _check(_data(None))
    assert check.status == "unknown"
    assert "exports no keepouts" in check.detail


def test_empty_keepouts_pass_and_unplaced_anchor_is_unknown() -> None:
    assert _check(_data([])).status == "pass"
    data = _data([BOARD])
    del data["imported_sources"][0]["anchor_points"][1]["position_mm"]
    assert _check(data).status == "unknown"


def test_no_mech_import_is_unknown_and_no_anchored_route_passes() -> None:
    data = _data([BOARD])
    data["imported_sources"] = []
    assert _check(data).status == "unknown"
    data = example_contract_data()
    assert _check(data).detail == "no route spans two anchors"


@pytest.mark.parametrize(
    "keepouts",
    [
        [{"name": "flat", "min_mm": [0.0, 0.0, 5.0], "max_mm": [1.0, 1.0, 5.0]}],
        [BOARD, BOARD],
    ],
    ids=["zero-extent", "duplicate"],
)
def test_malformed_keepouts_are_rejected(keepouts: list[dict[str, Any]]) -> None:
    with pytest.raises(ValidationError):
        HarnessContract.model_validate(_data(keepouts))


def test_keepouts_absent_keep_the_contract_digest() -> None:
    legacy = HarnessContract.model_validate(_data(None))
    assert "keepouts" not in legacy.model_dump_json()
    assert contract_sha256(legacy) != contract_sha256(HarnessContract.model_validate(_data([])))


def test_import_copies_keepouts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "x.mech-envelope.json"
    payload = {
        "schema_version": 1,
        "system": "mech",
        "anchors": [{"name": "A1", "position_mm": [0.0, 0.0, 0.0]}],
        "keepouts": [BOARD],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    contract = HarnessContract.model_validate(example_contract_data())
    merged = import_envelope(contract, EnvelopeSource.model_validate(payload), path)
    source = merged.imported_sources[-1]
    assert source.keepouts is not None
    assert [box.name for box in source.keepouts] == ["board"]

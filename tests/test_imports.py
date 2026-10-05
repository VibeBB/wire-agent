"""Connectivity / envelope import tests (ADR-0003)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from helpers import example_contract_data
from wire.contract import HarnessContract
from wire.gates import run_gates
from wire.imports import (
    import_connectivity,
    import_envelope,
    load_connectivity_csv,
    load_connectivity_source,
    load_envelope_source,
)


def _write(tmp_path: Path, name: str, data: dict[str, Any]) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


CIRCUIT = {
    "schema_version": 1,
    "system": "circuit",
    "connectors": [
        {
            "ref": "J3",
            "family_hint": "JST XH",
            "housing": "B2B-XH-A",
            "rated_current_a": 3.0,
            "rated_voltage_v": 250.0,
            "cavities": ["1", "2"],
        }
    ],
    "nets": [
        {
            "ref": "GND",
            "signal_class": "ground",
            "voltage_v": 0.0,
            "current_a": 0.5,
        }
    ],
}

ENVELOPE = {
    "schema_version": 1,
    "system": "mech",
    "anchors": [
        {"name": "clip-01", "kind": "clip", "position_mm": [100.0, 0.0, 40.0]},
        {"name": "grm-01", "kind": "grommet"},
    ],
}


def test_circuit_import_creates_stubs(tmp_path: Path) -> None:
    contract = HarnessContract.model_validate(example_contract_data())
    src = _write(tmp_path, "board.connectivity.json", CIRCUIT)
    merged = import_connectivity(contract, load_connectivity_source(src), src)
    ids = {c.id for c in merged.connectors}
    assert "C3" in ids
    n_ids = {n.id for n in merged.nets}
    assert "N4" in n_ids
    c3 = next(c for c in merged.connectors if c.id == "C3")
    assert c3.source is not None and c3.source.ref == "J3"
    imported = [s for s in merged.imported_sources if s.system == "circuit"]
    assert len(imported) == 1
    assert imported[0].sha256 == hashlib.sha256(src.read_bytes()).hexdigest()
    # Existing elements untouched
    assert len(merged.wires) == len(contract.wires)


def test_reimport_refreshes_instead_of_duplicating(tmp_path: Path) -> None:
    """Re-importing the same file keeps one I* entry and never duplicates elements."""
    contract = HarnessContract.model_validate(example_contract_data())
    src = _write(tmp_path, "board.connectivity.json", CIRCUIT)
    once = import_connectivity(contract, load_connectivity_source(src), src)
    twice = import_connectivity(once, load_connectivity_source(src), src)
    assert {c.id for c in twice.connectors} == {c.id for c in once.connectors}
    assert {n.id for n in twice.nets} == {n.id for n in once.nets}
    assert len(twice.imported_sources) == len(once.imported_sources)


def test_reimport_appends_only_new_refs(tmp_path: Path) -> None:
    contract = HarnessContract.model_validate(example_contract_data())
    src = _write(tmp_path, "board.connectivity.json", CIRCUIT)
    once = import_connectivity(contract, load_connectivity_source(src), src)
    grown = json.loads(json.dumps(CIRCUIT))
    grown["connectors"].append({"ref": "J4", "cavities": ["1"]})
    src.write_text(json.dumps(grown), encoding="utf-8")
    twice = import_connectivity(once, load_connectivity_source(src), src)
    assert len(twice.connectors) == len(once.connectors) + 1
    entry = twice.imported_sources[-1]
    assert entry.id == once.imported_sources[-1].id
    assert entry.sha256 == hashlib.sha256(src.read_bytes()).hexdigest()


def test_envelope_keeps_anchor_geometry(tmp_path: Path) -> None:
    contract = HarnessContract.model_validate(example_contract_data())
    src = _write(tmp_path, "housing.envelope.json", ENVELOPE)
    merged = import_envelope(contract, load_envelope_source(src), src)
    points = merged.anchor_map()
    assert points["clip-01"].position_mm == (100.0, 0.0, 40.0)
    assert points["clip-01"].kind == "clip"
    assert points["grm-01"].position_mm is None


def test_envelope_rejects_duplicate_anchor_names(tmp_path: Path) -> None:
    contract = HarnessContract.model_validate(example_contract_data())
    data = {"schema_version": 1, "system": "mech", "anchors": [{"name": "a"}, {"name": "a"}]}
    src = _write(tmp_path, "dup.envelope.json", data)
    with pytest.raises(ValueError, match="duplicate"):
        import_envelope(contract, load_envelope_source(src), src)


def _placed(tmp_path: Path, anchors: list[str], length_scale: float = 1.0) -> HarnessContract:
    contract = HarnessContract.model_validate(example_contract_data())
    src = _write(tmp_path, "housing.envelope.json", PLACED)
    merged = import_envelope(contract, load_envelope_source(src), src)
    data = merged.model_dump(mode="json")
    data["routes"][0]["anchors"] = anchors
    for segment in data["routes"][0]["segments"]:
        segment["length_m"] *= length_scale
    return HarnessContract.model_validate(data)


PLACED = {
    "schema_version": 1,
    "system": "mech",
    "anchors": [
        {"name": "a", "kind": "clip", "position_mm": [0.0, 0.0, 0.0]},
        {"name": "b", "kind": "clip", "position_mm": [300.0, 400.0, 0.0]},
        {"name": "c", "kind": "breakout"},
    ],
}


def _checks(contract: HarnessContract, check_id: str) -> list[str]:
    return [c.status for c in run_gates(contract).checks if c.id == check_id]


def test_route_geometry_passes_when_route_reaches_anchors(tmp_path: Path) -> None:
    # RT1 is 0.5 m long; a..b is 500 mm.
    assert _checks(_placed(tmp_path, ["a", "b"]), "route_geometry") == ["pass"]


def test_route_geometry_fails_when_route_too_short(tmp_path: Path) -> None:
    contract = _placed(tmp_path, ["a", "b"], length_scale=0.5)
    report = run_gates(contract)
    check = next(c for c in report.checks if c.id == "route_geometry")
    assert check.status == "fail"
    assert check.limit == 500.0
    assert report.verdict == "fail"


def test_route_geometry_unknown_without_positions(tmp_path: Path) -> None:
    assert _checks(_placed(tmp_path, ["a", "c"]), "route_geometry") == ["unknown"]


def test_import_freshness_tracks_source_bytes(tmp_path: Path) -> None:
    contract = HarnessContract.model_validate(example_contract_data())
    src = _write(tmp_path, "board.connectivity.json", CIRCUIT)
    merged = import_connectivity(contract, load_connectivity_source(src), src)
    assert _checks(merged, "import_freshness") == ["pass"]
    src.write_text(json.dumps({**CIRCUIT, "nets": []}), encoding="utf-8")
    assert _checks(merged, "import_freshness") == ["fail"]
    src.unlink()
    assert _checks(merged, "import_freshness") == ["unknown"]


def test_envelope_import_and_anchor_resolution(tmp_path: Path) -> None:
    contract = HarnessContract.model_validate(example_contract_data())
    src = _write(tmp_path, "housing.envelope.json", ENVELOPE)
    merged = import_envelope(contract, load_envelope_source(src), src)
    assert merged.imported_sources[-1].anchors == ["clip-01", "grm-01"]
    data = merged.model_dump(mode="json")
    data["routes"][0]["anchors"] = ["clip-01", "grm-01"]
    resolved = HarnessContract.model_validate(data)
    report = run_gates(resolved)
    anchor = [c for c in report.checks if c.id == "anchor_resolution"]
    assert anchor and all(c.status == "pass" for c in anchor)


def test_envelope_missing_anchor_fails(tmp_path: Path) -> None:
    contract = HarnessContract.model_validate(example_contract_data())
    src = _write(tmp_path, "housing.envelope.json", ENVELOPE)
    merged = import_envelope(contract, load_envelope_source(src), src)
    data = merged.model_dump(mode="json")
    data["routes"][0]["anchors"] = ["clip-99"]
    resolved = HarnessContract.model_validate(data)
    report = run_gates(resolved)
    anchor = [c for c in report.checks if c.id == "anchor_resolution"]
    assert anchor and all(c.status == "fail" for c in anchor)


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "upstream"


def test_upstream_connectivity_fixture(tmp_path: Path) -> None:
    """The canonical upstream ConnectivitySource fixture imports cleanly."""
    src = FIXTURES / "board.connectivity.json"
    source = load_connectivity_source(src)
    assert source.system == "circuit"
    contract = HarnessContract.model_validate(example_contract_data())
    merged = import_connectivity(contract, source, src)
    imported = [s for s in merged.imported_sources if s.system == "circuit"]
    assert len(imported) == 1
    assert imported[0].sha256 == hashlib.sha256(src.read_bytes()).hexdigest()
    assert {c.source.ref for c in merged.connectors if c.source} >= {"J1", "J2"}


def test_upstream_envelope_fixture(tmp_path: Path) -> None:
    """The canonical upstream EnvelopeSource fixture imports cleanly."""
    src = FIXTURES / "housing.envelope.json"
    source = load_envelope_source(src)
    assert source.system == "mech"
    assert [a.name for a in source.anchors] == ["clip-01", "clip-02", "breakout-01"]
    contract = HarnessContract.model_validate(example_contract_data())
    merged = import_envelope(contract, source, src)
    assert merged.imported_sources[-1].system == "mech"


def test_csv_connectivity(tmp_path: Path) -> None:
    csv_path = tmp_path / "wirelist.csv"
    csv_path.write_text(
        "from_connector,to_connector,from_cavity,to_cavity,net,signal_class,voltage_v,current_a\n"
        "J5,J6,1,1,+12V,power,12,1.5\n",
        encoding="utf-8",
    )
    source = load_connectivity_csv(csv_path)
    assert source.system == "csv"
    assert len(source.nets) == 1 and source.nets[0].voltage_v == 12.0
    assert {c.ref for c in source.connectors} == {"J5", "J6"}
    contract = HarnessContract.model_validate(example_contract_data())
    merged = import_connectivity(contract, source, csv_path)
    assert any(s.system == "csv" for s in merged.imported_sources)


def test_generic_family_imports_housing_as_mate(tmp_path: Path) -> None:
    """Connector_Generic families describe the mate, not a harness part."""
    generic: dict[str, Any] = {
        **CIRCUIT,
        "connectors": [
            {
                "ref": "J3",
                "family_hint": "Connector_Generic:Conn_01x02",
                "housing": "B2B-XH-A",
                "rated_current_a": 3.0,
                "rated_voltage_v": 250.0,
                "cavities": ["1", "2"],
            }
        ],
    }
    contract = HarnessContract.model_validate(example_contract_data())
    src = _write(tmp_path, "board.connectivity.json", generic)
    merged = import_connectivity(contract, load_connectivity_source(src), src)
    c3 = next(c for c in merged.connectors if c.id == "C3")
    assert c3.mate == "B2B-XH-A"
    assert c3.housing is None


def test_named_family_keeps_housing_and_net_ref(tmp_path: Path) -> None:
    contract = HarnessContract.model_validate(example_contract_data())
    src = _write(tmp_path, "board.connectivity.json", CIRCUIT)
    merged = import_connectivity(contract, load_connectivity_source(src), src)
    c3 = next(c for c in merged.connectors if c.id == "C3")
    assert c3.housing == "B2B-XH-A"
    assert c3.mate is None
    n4 = next(n for n in merged.nets if n.id == "N4")
    assert n4.ref == "GND"

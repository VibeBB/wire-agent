"""Connectivity and envelope import adapters (ADR-0003).

External contract files are validated, copied into the harness contract as
declared elements with provenance, and recorded in ``imported_sources``.
The contract never links back: the copy is the truth, and a later re-import
produces a diff, not live coupling.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .contract import (
    HarnessContract,
)

CONNECTIVITY_SYSTEMS = ("circuit", "csv", "kbl", "vec")


class SourceConnector(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str = Field(min_length=1)
    family_hint: str | None = None
    housing: str | None = None
    rated_current_a: float = Field(default=3.0, gt=0)
    rated_voltage_v: float = Field(default=250.0, gt=0)
    cavities: list[str] = Field(min_length=1)


class SourceNet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str = Field(min_length=1)
    signal_class: Literal["power", "ground", "signal", "analog", "data", "highspeed", "shield"] = (
        "signal"
    )
    voltage_v: float = Field(ge=0)
    current_a: float = Field(ge=0)


class ConnectivitySource(BaseModel):
    """Normalized connectivity view exported by an upstream agent."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    system: Literal["circuit", "csv", "kbl", "vec"] = "circuit"
    connectors: list[SourceConnector] = Field(default_factory=list[SourceConnector])
    nets: list[SourceNet] = Field(default_factory=list[SourceNet])


class EnvelopeAnchor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    kind: Literal["clip", "grommet", "breakout", "other"] = "other"
    position_mm: tuple[float, float, float] | None = None


class EnvelopeSource(BaseModel):
    """Fixturing points exported by the mechanical envelope."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    system: Literal["mech"] = "mech"
    anchors: list[EnvelopeAnchor] = Field(min_length=1)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_connectivity_source(path: Path) -> ConnectivitySource:
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not load connectivity source {path}: {exc}") from exc
    return ConnectivitySource.model_validate(value)


def load_envelope_source(path: Path) -> EnvelopeSource:
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not load envelope source {path}: {exc}") from exc
    return EnvelopeSource.model_validate(value)


def _next_id(prefix: str, used: set[str]) -> str:
    index = 1
    while f"{prefix}{index}" in used:
        index += 1
    return f"{prefix}{index}"


def import_connectivity(
    contract: HarnessContract,
    source: ConnectivitySource,
    source_path: Path,
) -> HarnessContract:
    """Merge a connectivity source into the contract with provenance.

    Existing connectors/nets are left untouched; new elements are appended
    with deterministic C*/N* ids. The source file's sha256 is recorded.
    """
    data = contract.model_dump()
    used_c = {c["id"] for c in data["connectors"]}
    used_n = {n["id"] for n in data["nets"]}
    used_i = {s["id"] for s in data["imported_sources"]}
    digest = _sha256_file(source_path)
    source_id = _next_id("I", used_i)
    data["imported_sources"].append(
        {
            "id": source_id,
            "system": source.system,
            "ref": str(source_path),
            "sha256": digest,
            "description": f"{len(source.connectors)} connectors, {len(source.nets)} nets",
        }
    )
    for conn in source.connectors:
        cid = _next_id("C", used_c)
        used_c.add(cid)
        data["connectors"].append(
            {
                "id": cid,
                "family": conn.family_hint or "imported",
                "housing": conn.housing,
                "rated_current_a": conn.rated_current_a,
                "rated_voltage_v": conn.rated_voltage_v,
                "cavities": [{"id": cavity} for cavity in conn.cavities],
                "source": {
                    "system": source.system,
                    "ref": conn.ref,
                    "sha256": digest,
                },
            }
        )
    for net in source.nets:
        nid = _next_id("N", used_n)
        used_n.add(nid)
        data["nets"].append(
            {
                "id": nid,
                "signal_class": net.signal_class,
                "voltage_v": net.voltage_v,
                "current_a": net.current_a,
                "source": {
                    "system": source.system,
                    "ref": net.ref,
                    "sha256": digest,
                },
            }
        )
    return HarnessContract.model_validate(data)


def import_envelope(
    contract: HarnessContract,
    source: EnvelopeSource,
    source_path: Path,
) -> HarnessContract:
    """Record an envelope source; its anchor names become resolvable."""
    data = contract.model_dump()
    used_i = {s["id"] for s in data["imported_sources"]}
    digest = _sha256_file(source_path)
    source_id = _next_id("I", used_i)
    data["imported_sources"].append(
        {
            "id": source_id,
            "system": "mech",
            "ref": str(source_path),
            "sha256": digest,
            "description": f"{len(source.anchors)} anchors",
            "anchors": [anchor.name for anchor in source.anchors],
        }
    )
    return HarnessContract.model_validate(data)


def load_connectivity_csv(path: Path) -> ConnectivitySource:
    """Parse a generic From/To CSV into a normalized connectivity source.

    Required columns: from_connector, to_connector. Optional:
    from_cavity, to_cavity, net, signal_class, voltage_v, current_a,
    family_hint, housing.
    """
    connectors: dict[str, SourceConnector] = {}
    nets: dict[str, SourceNet] = {}
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                for key in ("from_connector", "to_connector"):
                    ref = (row.get(key) or "").strip()
                    if not ref:
                        continue
                    cavity_col = "from_cavity" if key == "from_connector" else "to_cavity"
                    cavity = (row.get(cavity_col) or "").strip()
                    if ref not in connectors:
                        connectors[ref] = SourceConnector(
                            ref=ref,
                            family_hint=(row.get("family_hint") or None),
                            housing=(row.get("housing") or None),
                            cavities=[cavity] if cavity else ["1"],
                        )
                    elif cavity and cavity not in connectors[ref].cavities:
                        connectors[ref].cavities.append(cavity)
                net_ref = (row.get("net") or "").strip()
                if net_ref and net_ref not in nets:
                    nets[net_ref] = SourceNet(
                        ref=net_ref,
                        signal_class=(row.get("signal_class") or "signal"),  # type: ignore[arg-type]
                        voltage_v=float(row.get("voltage_v") or 0),
                        current_a=float(row.get("current_a") or 0),
                    )
    except OSError as exc:
        raise ValueError(f"could not read CSV {path}: {exc}") from exc
    return ConnectivitySource(
        system="csv",
        connectors=list(connectors.values()),
        nets=list(nets.values()),
    )

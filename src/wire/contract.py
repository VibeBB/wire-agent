"""Machine-readable wire harness contract models and helpers.

The contract is the single source of truth for a design. Every artifact is a
projection of these bytes; nothing flows back into the contract.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SIGNAL_CLASSES: tuple[str, ...] = (
    "power",
    "ground",
    "signal",
    "analog",
    "data",
    "highspeed",
    "shield",
)

PROTECTION_KINDS: tuple[str, ...] = ("none", "tape", "tube", "conduit", "sleeve")
SHIELD_KINDS: tuple[str, ...] = ("none", "braid", "foil")
FLEX_CLASSES: tuple[str, ...] = ("static", "dynamic", "high_flex")
SOURCE_SYSTEMS: tuple[str, ...] = ("manual", "circuit", "mech", "csv", "kbl", "vec")


class ElementSource(BaseModel):
    """Provenance of one element copied from an external contract."""

    model_config = ConfigDict(extra="forbid")

    system: Literal["manual", "circuit", "mech", "csv", "kbl", "vec"]
    ref: str = Field(min_length=1)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class TemperatureDeratingPoint(BaseModel):
    """One point on the ampacity derating curve (factor at ambient °C)."""

    model_config = ConfigDict(extra="forbid")

    temperature_c: float
    factor: float = Field(ge=0, le=1)


class CavitySpec(BaseModel):
    """A connector cavity that accepts one wire termination."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    accepts_mm2: tuple[float, float] | None = None
    terminal: str | None = None

    @model_validator(mode="after")
    def validate_range(self) -> CavitySpec:
        if self.accepts_mm2 is not None:
            lo, hi = self.accepts_mm2
            if lo <= 0 or hi < lo:
                raise ValueError("accepts_mm2 must be (min, max) with 0 < min <= max")
        return self


class HarnessConnector(BaseModel):
    """A connector housing with its cavity table and electrical ratings."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^C[0-9]+$")
    family: str = Field(min_length=1)
    housing: str | None = None
    mate: str | None = None
    rated_current_a: float = Field(gt=0)
    rated_voltage_v: float = Field(gt=0)
    mating_cycles: int = Field(default=30, ge=1)
    keying: str | None = None
    sealed: bool = False
    temp_rating_c: float | None = None
    cavity_count: int | None = Field(default=None, ge=1)
    cavities: list[CavitySpec] = Field(min_length=1)
    source: ElementSource | None = None

    @model_validator(mode="after")
    def validate_cavities(self) -> HarnessConnector:
        ids = [cavity.id for cavity in self.cavities]
        if len(set(ids)) != len(ids):
            raise ValueError("cavity ids must be unique within a connector")
        if self.cavity_count is not None and len(self.cavities) > self.cavity_count:
            raise ValueError("cavity_count smaller than declared cavities")
        return self


class WireType(BaseModel):
    """A wire specification: gauge, ampacity, insulation, bend, flex."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^WT[0-9]+$")
    name: str = Field(min_length=1)
    spec: str | None = None
    gauge_mm2: float = Field(gt=0)
    outer_diameter_mm: float = Field(gt=0)
    resistance_ohm_per_km: float = Field(gt=0)
    ampacity_a: float = Field(gt=0)
    reference_temp_c: float
    temp_derating: list[TemperatureDeratingPoint] = Field(
        default_factory=list[TemperatureDeratingPoint]
    )
    insulation_rating_v: float = Field(gt=0)
    insulation_temp_c: float
    min_bend_factor: float = Field(gt=0)  # multiplier on outer_diameter_mm
    shield: Literal["none", "braid", "foil"] = "none"
    flex_class: Literal["static", "dynamic", "high_flex"] = "static"
    source: ElementSource | None = None

    @model_validator(mode="after")
    def validate_derating(self) -> WireType:
        temps = [point.temperature_c for point in self.temp_derating]
        if temps != sorted(temps):
            raise ValueError("temp_derating must be sorted by temperature_c")
        return self


class Endpoint(BaseModel):
    """One termination: a connector cavity, or a leg on a splice junction."""

    model_config = ConfigDict(extra="forbid")

    connector: str | None = Field(default=None, pattern=r"^C[0-9]+$")
    cavity: str | None = Field(default=None, min_length=1)
    splice: str | None = Field(default=None, pattern=r"^SP[0-9]+$")

    @model_validator(mode="after")
    def validate_endpoint(self) -> Endpoint:
        if self.splice is not None:
            if self.connector is not None or self.cavity is not None:
                raise ValueError("splice endpoints cannot set connector or cavity")
        elif self.connector is None or self.cavity is None:
            raise ValueError("endpoints need connector+cavity or splice")
        return self


class HarnessSplice(BaseModel):
    """A galvanic junction joining several wire legs (crimp/solder/ferrule)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^SP[0-9]+$")
    kind: Literal["crimp", "solder", "ultrasonic", "ferrule"] = "crimp"
    source: ElementSource | None = None


class HarnessWire(BaseModel):
    """A wire connecting two endpoints on a declared net over a route."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^W[0-9]+$")
    wire_type: str = Field(pattern=r"^WT[0-9]+$")
    net: str = Field(pattern=r"^N[0-9]+$")
    color: str | None = None
    from_endpoint: Endpoint
    to_endpoint: Endpoint
    length_m: float = Field(gt=0)
    strip_a_mm: float = Field(default=4.0, gt=0)
    strip_b_mm: float = Field(default=4.0, gt=0)
    terminal_a: str | None = None
    terminal_b: str | None = None
    route: str | None = Field(default=None, pattern=r"^RT[0-9]+$")


class RouteSegment(BaseModel):
    """One declared path segment with its tightest bend."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^S[0-9]+$")
    length_m: float = Field(gt=0)
    min_bend_radius_mm: float | None = Field(default=None, gt=0)


class HarnessRoute(BaseModel):
    """A bundle path: segments carrying wires, with protection and anchors."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^RT[0-9]+$")
    segments: list[RouteSegment] = Field(min_length=1)
    protection: Literal["none", "tape", "tube", "conduit", "sleeve"] = "none"
    flex_required: bool = False
    anchors: list[str] = Field(default_factory=list[str])

    @model_validator(mode="after")
    def validate_segments(self) -> HarnessRoute:
        ids = [segment.id for segment in self.segments]
        if len(set(ids)) != len(ids):
            raise ValueError("segment ids must be unique within a route")
        return self


class HarnessNet(BaseModel):
    """A declared electrical net with its electrical class and demand."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^N[0-9]+$")
    ref: str | None = None
    signal_class: Literal["power", "ground", "signal", "analog", "data", "highspeed", "shield"]
    voltage_v: float = Field(ge=0)
    current_a: float = Field(ge=0)
    max_voltage_drop_v: float | None = Field(default=None, ge=0)
    shield_required: bool = False
    twisted_pair_with: str | None = Field(default=None, pattern=r"^N[0-9]+$")
    source: ElementSource | None = None


class SegregationPolicy(BaseModel):
    """Two signal classes that must not share the given scope."""

    model_config = ConfigDict(extra="forbid")

    classes: tuple[
        Literal["power", "ground", "signal", "analog", "data", "highspeed", "shield"],
        Literal["power", "ground", "signal", "analog", "data", "highspeed", "shield"],
    ]
    rule: Literal["no_shared_route", "no_shared_connector"]


class ServiceExpectation(BaseModel):
    """Expected service conditions the design must meet."""

    model_config = ConfigDict(extra="forbid")

    mating_cycles: int | None = Field(default=None, ge=1)
    flex_cycles: int | None = Field(default=None, ge=1)


class ImportedSource(BaseModel):
    """An external file whose contents were copied into the contract."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^I[0-9]+$")
    system: Literal["manual", "circuit", "mech", "csv", "kbl", "vec"]
    ref: str = Field(min_length=1)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    description: str = ""
    anchors: list[str] = Field(default_factory=list[str])


class HarnessContract(BaseModel):
    """The wire harness contract: the single source of truth for a design."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    contract_id: str = Field(pattern=r"^WH-[0-9A-Za-z-]+$")
    name: str = Field(min_length=1)
    revision: str = Field(min_length=1)
    ipc_class: Literal[1, 2, 3] = 2
    ambient_temperature_c: float = 25.0
    connectors: list[HarnessConnector] = Field(default_factory=list[HarnessConnector])
    wire_types: list[WireType] = Field(default_factory=list[WireType])
    nets: list[HarnessNet] = Field(default_factory=list[HarnessNet])
    wires: list[HarnessWire] = Field(default_factory=list[HarnessWire])
    routes: list[HarnessRoute] = Field(default_factory=list[HarnessRoute])
    splices: list[HarnessSplice] = Field(default_factory=list[HarnessSplice])
    segregations: list[SegregationPolicy] = Field(default_factory=list[SegregationPolicy])
    service: ServiceExpectation | None = None
    imported_sources: list[ImportedSource] = Field(default_factory=list[ImportedSource])

    @model_validator(mode="after")
    def validate_contract(self) -> HarnessContract:
        for collection, label in (
            (self.connectors, "connector"),
            (self.wire_types, "wire type"),
            (self.nets, "net"),
            (self.wires, "wire"),
            (self.routes, "route"),
            (self.splices, "splice"),
            (self.imported_sources, "imported source"),
        ):
            ids = [element.id for element in collection]
            if len(set(ids)) != len(ids):
                raise ValueError(f"{label} ids must be unique")
        connector_ids = {connector.id for connector in self.connectors}
        cavities = {
            (connector.id, cavity.id)
            for connector in self.connectors
            for cavity in connector.cavities
        }
        splice_ids = {splice.id for splice in self.splices}
        wire_type_ids = {wire_type.id for wire_type in self.wire_types}
        net_ids = {net.id for net in self.nets}
        route_ids = {route.id for route in self.routes}
        for net in self.nets:
            if net.twisted_pair_with is not None and net.twisted_pair_with not in net_ids:
                raise ValueError(f"net {net.id} twisted pair references unknown net")
        for wire in self.wires:
            if wire.wire_type not in wire_type_ids:
                raise ValueError(f"wire {wire.id} references unknown wire type")
            if wire.net not in net_ids:
                raise ValueError(f"wire {wire.id} references unknown net")
            if wire.route is not None and wire.route not in route_ids:
                raise ValueError(f"wire {wire.id} references unknown route")
            for endpoint in (wire.from_endpoint, wire.to_endpoint):
                if endpoint.splice is not None:
                    if endpoint.splice not in splice_ids:
                        raise ValueError(f"wire {wire.id} references unknown splice")
                elif endpoint.connector not in connector_ids:
                    raise ValueError(f"wire {wire.id} references unknown connector")
                elif (endpoint.connector, endpoint.cavity) not in cavities:
                    raise ValueError(
                        f"wire {wire.id} references unknown cavity "
                        f"{endpoint.connector}:{endpoint.cavity}"
                    )
        return self

    def element_ids(self) -> list[str]:
        """Deterministic ids of every addressable contract element."""
        ids: list[str] = []
        ids.extend(connector.id for connector in self.connectors)
        ids.extend(wire_type.id for wire_type in self.wire_types)
        ids.extend(net.id for net in self.nets)
        ids.extend(wire.id for wire in self.wires)
        ids.extend(route.id for route in self.routes)
        ids.extend(splice.id for splice in self.splices)
        return ids

    def connector_map(self) -> dict[str, HarnessConnector]:
        return {connector.id: connector for connector in self.connectors}

    def wire_type_map(self) -> dict[str, WireType]:
        return {wire_type.id: wire_type for wire_type in self.wire_types}

    def net_map(self) -> dict[str, HarnessNet]:
        return {net.id: net for net in self.nets}

    def route_map(self) -> dict[str, HarnessRoute]:
        return {route.id: route for route in self.routes}

    def splice_map(self) -> dict[str, HarnessSplice]:
        return {splice.id: splice for splice in self.splices}


def contract_sha256(contract: HarnessContract) -> str:
    """Canonical JSON digest used by the intake sidecar and provenance."""
    payload = contract.model_dump_json()
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_contract(path: Path) -> HarnessContract:
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not load harness contract {path}: {exc}") from exc
    return HarnessContract.model_validate(value)

"""Deterministic harness gates — the only pass/fail authority.

Every check emits a structured result: status is "pass", "fail", or
"unknown"; "unknown" and "fail" both make the design verdict fail
(fail-closed). Checks operate on the contract and, for manifest integrity,
the exported artifacts.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .contract import HarnessContract, HarnessWire, contract_sha256
from .standards import (
    DEFAULT_VOLTAGE_DROP_FRACTION,
    SPEC_DERATING,
    bundle_derating,
    temperature_factor,
)

CheckStatus = Literal["pass", "fail", "unknown"]


@dataclass(frozen=True)
class GateCheck:
    id: str
    subject: str
    status: CheckStatus
    measured: float | None = None
    limit: float | None = None
    detail: str = ""


@dataclass(frozen=True)
class GateReport:
    checks: list[GateCheck]
    verdict: Literal["pass", "fail"]

    def to_dict(self, contract: HarnessContract) -> dict[str, Any]:
        summary = {
            "pass": sum(1 for c in self.checks if c.status == "pass"),
            "fail": sum(1 for c in self.checks if c.status == "fail"),
            "unknown": sum(1 for c in self.checks if c.status == "unknown"),
        }
        return {
            "schema_version": 1,
            "gate": "wire-harness",
            "design": {
                "name": contract.name,
                "contract_id": contract.contract_id,
                "revision": contract.revision,
                "contract_sha256": contract_sha256(contract),
            },
            "verdict": self.verdict,
            "summary": summary,
            "checks": [
                {
                    "id": c.id,
                    "subject": c.subject,
                    "status": c.status,
                    "measured": c.measured,
                    "limit": c.limit,
                    "detail": c.detail,
                }
                for c in self.checks
            ],
        }


def _wrap(check_id: str, fn: Any, *args: Any) -> list[GateCheck]:
    try:
        return fn(*args)
    except Exception as exc:  # fail-closed: unexpected error → unknown
        return [GateCheck(check_id, check_id, "unknown", detail=f"check error: {exc}")]


def _route_wire_map(contract: HarnessContract) -> dict[str | None, list[HarnessWire]]:
    grouped: dict[str | None, list[HarnessWire]] = {}
    for wire in contract.wires:
        grouped.setdefault(wire.route, []).append(wire)
    return grouped


def _check_connectivity(contract: HarnessContract) -> list[GateCheck]:
    problems: list[str] = []
    connectors = contract.connector_map()
    routes = contract.route_map()
    for wire in contract.wires:
        for endpoint in (wire.from_endpoint, wire.to_endpoint):
            connector = connectors.get(endpoint.connector)
            if connector is None:
                problems.append(f"{wire.id}: unknown connector {endpoint.connector}")
            elif not any(c.id == endpoint.cavity for c in connector.cavities):
                problems.append(f"{wire.id}: unknown cavity {endpoint.connector}:{endpoint.cavity}")
        if wire.route is not None and wire.route not in routes:
            problems.append(f"{wire.id}: unknown route {wire.route}")
        if wire.from_endpoint == wire.to_endpoint:
            problems.append(f"{wire.id}: both endpoints identical")
    status: CheckStatus = "pass" if not problems else "fail"
    return [GateCheck("connectivity", "endpoints resolve", status, detail="; ".join(problems))]


def _check_cavity_occupancy(contract: HarnessContract) -> list[GateCheck]:
    seen: dict[tuple[str, str], str] = {}
    problems: list[str] = []
    for wire in contract.wires:
        for endpoint in (wire.from_endpoint, wire.to_endpoint):
            key = (endpoint.connector, endpoint.cavity)
            if key in seen:
                problems.append(
                    f"{endpoint.connector}:{endpoint.cavity} used by {seen[key]} and {wire.id}"
                )
            else:
                seen[key] = wire.id
    status: CheckStatus = "pass" if not problems else "fail"
    return [
        GateCheck("cavity_occupancy", "one wire per cavity", status, detail="; ".join(problems))
    ]


def _check_netlist_coverage(contract: HarnessContract) -> list[GateCheck]:
    used = {wire.net for wire in contract.wires}
    uncovered = [net.id for net in contract.nets if net.id not in used]
    status: CheckStatus = "pass" if not uncovered else "fail"
    return [
        GateCheck(
            "netlist_coverage",
            "every declared net carries a wire",
            status,
            detail="; ".join(f"{n} has no wire" for n in uncovered),
        )
    ]


def _check_shielding_pairing(contract: HarnessContract) -> list[GateCheck]:
    checks: list[GateCheck] = []
    nets = contract.net_map()
    types = contract.wire_type_map()
    problems: list[str] = []
    unknowns: list[str] = []
    for wire in contract.wires:
        net = nets[wire.net]
        wtype = types[wire.wire_type]
        if net.shield_required and wtype.shield == "none":
            problems.append(f"{wire.id}: net {net.id} requires shield, type {wtype.id} has none")
    status: CheckStatus = "fail" if problems else ("unknown" if unknowns else "pass")
    checks.append(
        GateCheck("shielding_pairing", "shield requirements", status, detail="; ".join(problems))
    )

    pair_problems: list[str] = []
    for net in contract.nets:
        if net.twisted_pair_with is None:
            continue
        pair = nets.get(net.twisted_pair_with)
        if pair is None:
            pair_problems.append(f"{net.id}: pair {net.twisted_pair_with} unknown")
            continue
        routes_a = {w.route for w in contract.wires if w.net == net.id}
        routes_b = {w.route for w in contract.wires if w.net == pair.id}
        if routes_a != routes_b or None in routes_a:
            pair_problems.append(
                f"{net.id}/{pair.id}: wires do not share one route "
                f"({sorted(str(r) for r in routes_a)} vs "
                f"{sorted(str(r) for r in routes_b)})"
            )
    status = "pass" if not pair_problems else "fail"
    checks.append(
        GateCheck(
            "shielding_pairing",
            "twisted-pair routing",
            status,
            detail="; ".join(pair_problems),
        )
    )
    return checks


def _ampacity_details(contract: HarnessContract) -> list[GateCheck]:
    checks: list[GateCheck] = []
    nets = contract.net_map()
    types = contract.wire_type_map()
    grouped = _route_wire_map(contract)
    for wire in contract.wires:
        wtype = types[wire.wire_type]
        net = nets[wire.net]
        bundle_size = len(grouped.get(wire.route, [wire]))
        curve = [(p.temperature_c, p.factor) for p in wtype.temp_derating]
        if not curve and wtype.spec:
            curve = list(SPEC_DERATING.get(wtype.spec, []))
        if not curve:
            if contract.ambient_temperature_c <= wtype.reference_temp_c:
                temp_factor = 1.0
            else:
                checks.append(
                    GateCheck(
                        "ampacity",
                        wire.id,
                        "unknown",
                        detail=f"no derating curve above reference {wtype.reference_temp_c}°C",
                    )
                )
                continue
        else:
            factor = temperature_factor(curve, contract.ambient_temperature_c)
            if factor is None or factor <= 0:
                checks.append(
                    GateCheck(
                        "ampacity",
                        wire.id,
                        "fail",
                        measured=contract.ambient_temperature_c,
                        limit=wtype.insulation_temp_c,
                        detail="ambient above derating curve",
                    )
                )
                continue
            temp_factor = factor
        effective = wtype.ampacity_a * temp_factor * bundle_derating(bundle_size)
        if net.current_a <= effective:
            status: CheckStatus = "pass"
        else:
            status = "fail"
        checks.append(
            GateCheck(
                "ampacity",
                wire.id,
                status,
                measured=round(net.current_a, 4),
                limit=round(effective, 4),
                detail=(
                    f"bundle {bundle_size}, temp factor {round(temp_factor, 3)}, "
                    f"route {wire.route or '-'}"
                ),
            )
        )
    return checks


def _check_voltage_drop(contract: HarnessContract) -> list[GateCheck]:
    checks: list[GateCheck] = []
    nets = contract.net_map()
    types = contract.wire_type_map()
    for wire in contract.wires:
        wtype = types[wire.wire_type]
        net = nets[wire.net]
        if net.max_voltage_drop_v is not None:
            limit = net.max_voltage_drop_v
        elif net.voltage_v > 0:
            limit = net.voltage_v * DEFAULT_VOLTAGE_DROP_FRACTION
        else:
            checks.append(
                GateCheck(
                    "voltage_drop",
                    wire.id,
                    "unknown",
                    detail="0 V net needs an explicit max_voltage_drop_v",
                )
            )
            continue
        drop = net.current_a * (wire.length_m / 1000.0) * wtype.resistance_ohm_per_km
        checks.append(
            GateCheck(
                "voltage_drop",
                wire.id,
                "pass" if drop <= limit else "fail",
                measured=round(drop, 5),
                limit=round(limit, 5),
                detail=f"length {wire.length_m} m, R {wtype.resistance_ohm_per_km} ohm/km",
            )
        )
    return checks


def _check_insulation_rating(contract: HarnessContract) -> list[GateCheck]:
    checks: list[GateCheck] = []
    nets = contract.net_map()
    types = contract.wire_type_map()
    for wire in contract.wires:
        wtype = types[wire.wire_type]
        net = nets[wire.net]
        voltage_ok = net.voltage_v <= wtype.insulation_rating_v
        temp_ok = contract.ambient_temperature_c <= wtype.insulation_temp_c
        detail = (
            f"voltage {net.voltage_v}/{wtype.insulation_rating_v} V, "
            f"ambient {contract.ambient_temperature_c}/{wtype.insulation_temp_c}°C"
        )
        checks.append(
            GateCheck(
                "insulation_rating",
                wire.id,
                "pass" if voltage_ok and temp_ok else "fail",
                measured=max(
                    net.voltage_v / wtype.insulation_rating_v,
                    contract.ambient_temperature_c / wtype.insulation_temp_c,
                ),
                limit=1.0,
                detail=detail,
            )
        )
    return checks


def _check_bend_radius(contract: HarnessContract) -> list[GateCheck]:
    checks: list[GateCheck] = []
    types = contract.wire_type_map()
    grouped = _route_wire_map(contract)
    unrouted = grouped.get(None, [])
    if unrouted:
        checks.append(
            GateCheck(
                "bend_radius",
                "route coverage",
                "unknown",
                detail=f"wires without a route: {', '.join(w.id for w in unrouted)}",
            )
        )
    for route in contract.routes:
        wires = grouped.get(route.id, [])
        required = 0.0
        for wire in wires:
            wtype = types[wire.wire_type]
            required = max(required, wtype.min_bend_factor * wtype.outer_diameter_mm)
        flex_types = {types[w.wire_type].flex_class for w in wires}
        if route.flex_required and "static" in flex_types:
            checks.append(
                GateCheck(
                    "bend_radius",
                    route.id,
                    "fail",
                    detail="route requires flex but carries static-class wire",
                )
            )
        for segment in route.segments:
            if segment.min_bend_radius_mm is None:
                checks.append(
                    GateCheck(
                        "bend_radius",
                        f"{route.id}:{segment.id}",
                        "unknown",
                        detail="no min_bend_radius_mm declared",
                    )
                )
                continue
            checks.append(
                GateCheck(
                    "bend_radius",
                    f"{route.id}:{segment.id}",
                    "pass" if segment.min_bend_radius_mm >= required else "fail",
                    measured=segment.min_bend_radius_mm,
                    limit=round(required, 3),
                    detail=f"protection {route.protection}, wires {len(wires)}",
                )
            )
    return checks


def _check_segregation(contract: HarnessContract) -> list[GateCheck]:
    checks: list[GateCheck] = []
    nets = contract.net_map()
    grouped = _route_wire_map(contract)
    connector_wires: dict[str, list[HarnessWire]] = {}
    for wire in contract.wires:
        connector_wires.setdefault(wire.from_endpoint.connector, []).append(wire)
        connector_wires.setdefault(wire.to_endpoint.connector, []).append(wire)

    for policy in contract.segregations:
        class_a, class_b = sorted(policy.classes)
        if policy.rule == "no_shared_route":
            problems: list[str] = []
            unknowns: list[str] = []
            for route_id, wires in grouped.items():
                classes = {nets[w.net].signal_class for w in wires}
                if class_a in classes and class_b in classes:
                    label = route_id if route_id is not None else "(unrouted)"
                    problems.append(f"{label}: {class_a}+{class_b}")
            if None in grouped:
                unknowns.append("wires without route cannot be segregated")
            if problems:
                status: CheckStatus = "fail"
            elif unknowns:
                status = "unknown"
            else:
                status = "pass"
            checks.append(
                GateCheck(
                    "segregation",
                    f"{class_a}/{class_b} route",
                    status,
                    detail="; ".join(problems + unknowns),
                )
            )
        else:  # no_shared_connector
            problems = []
            for connector_id, wires in connector_wires.items():
                classes = {nets[w.net].signal_class for w in wires}
                if class_a in classes and class_b in classes:
                    problems.append(f"{connector_id}: {class_a}+{class_b}")
            checks.append(
                GateCheck(
                    "segregation",
                    f"{class_a}/{class_b} connector",
                    "pass" if not problems else "fail",
                    detail="; ".join(problems),
                )
            )
    return checks


def _check_terminal_compatibility(contract: HarnessContract) -> list[GateCheck]:
    checks: list[GateCheck] = []
    connectors = contract.connector_map()
    types = contract.wire_type_map()
    for wire in contract.wires:
        wtype = types[wire.wire_type]
        for endpoint, terminal in (
            (wire.from_endpoint, wire.terminal_a),
            (wire.to_endpoint, wire.terminal_b),
        ):
            connector = connectors[endpoint.connector]
            cavity = next(c for c in connector.cavities if c.id == endpoint.cavity)
            subject = f"{wire.id}:{endpoint.connector}:{endpoint.cavity}"
            problems: list[str] = []
            unknowns: list[str] = []
            if cavity.accepts_mm2 is None:
                unknowns.append("no accepts_mm2 declared")
            else:
                lo, hi = cavity.accepts_mm2
                if not lo <= wtype.gauge_mm2 <= hi:
                    problems.append(f"gauge {wtype.gauge_mm2} outside {lo}-{hi} mm2")
            if terminal is not None and cavity.terminal is not None:
                if terminal != cavity.terminal:
                    problems.append(f"terminal {terminal} != cavity {cavity.terminal}")
            elif terminal is None or cavity.terminal is None:
                unknowns.append("terminal not fully declared")
            if problems:
                status: CheckStatus = "fail"
            elif unknowns:
                status = "unknown"
            else:
                status = "pass"
            checks.append(
                GateCheck(
                    "terminal_compatibility",
                    subject,
                    status,
                    detail="; ".join(problems + unknowns),
                )
            )
    return checks


def _check_connector_rating(contract: HarnessContract) -> list[GateCheck]:
    checks: list[GateCheck] = []
    connectors = contract.connector_map()
    nets = contract.net_map()
    grouped_housing: dict[tuple[str, str | None, int], list[str]] = {}
    for connector in contract.connectors:
        key = (connector.family, connector.housing, len(connector.cavities))
        grouped_housing.setdefault(key, []).append(connector.id)

        wires_here = [
            w
            for w in contract.wires
            if w.from_endpoint.connector == connector.id or w.to_endpoint.connector == connector.id
        ]
        max_i = max((nets[w.net].current_a for w in wires_here), default=0.0)
        max_v = max((nets[w.net].voltage_v for w in wires_here), default=0.0)
        problems: list[str] = []
        if connector.cavity_count is not None and len(connector.cavities) > connector.cavity_count:
            problems.append(
                f"{len(connector.cavities)} cavities > housing {connector.cavity_count}"
            )
        if max_i > connector.rated_current_a:
            problems.append(f"current {max_i} A > {connector.rated_current_a} A")
        if max_v > connector.rated_voltage_v:
            problems.append(f"voltage {max_v} V > {connector.rated_voltage_v} V")
        if (
            contract.service is not None
            and contract.service.mating_cycles is not None
            and contract.service.mating_cycles > connector.mating_cycles
        ):
            problems.append(
                f"expected mating {contract.service.mating_cycles} "
                f"> rated {connector.mating_cycles}"
            )
        if (
            connector.temp_rating_c is not None
            and contract.ambient_temperature_c > connector.temp_rating_c
        ):
            problems.append(
                f"ambient {contract.ambient_temperature_c}°C > rating {connector.temp_rating_c}°C"
            )
        checks.append(
            GateCheck(
                "connector_rating",
                connector.id,
                "pass" if not problems else "fail",
                measured=max_i,
                limit=connector.rated_current_a,
                detail="; ".join(problems),
            )
        )
    for key, connector_ids in grouped_housing.items():
        if len(connector_ids) < 2:
            continue
        keyings = {connectors[c].keying for c in connector_ids}
        if len(keyings) != len(connector_ids) or None in keyings:
            checks.append(
                GateCheck(
                    "connector_rating",
                    f"keying {key[0]} x{len(connector_ids)}",
                    (
                        "fail"
                        if None not in keyings and len(keyings) != len(connector_ids)
                        else "unknown"
                    ),
                    detail=f"identical housings {connector_ids} need distinct keying",
                )
            )
    return checks


def _check_anchor_resolution(contract: HarnessContract) -> list[GateCheck]:
    declared = {anchor for route in contract.routes for anchor in route.anchors}
    if not declared:
        return [GateCheck("anchor_resolution", "anchors", "pass", detail="no anchors declared")]
    available: set[str] = set()
    for source in contract.imported_sources:
        available.update(source.anchors)
    if not any(s.system == "mech" for s in contract.imported_sources):
        return [
            GateCheck(
                "anchor_resolution",
                "anchors",
                "unknown",
                detail="anchors declared but no mech envelope imported",
            )
        ]
    missing = sorted(anchor for anchor in declared if anchor not in available)
    status: CheckStatus = "pass" if not missing else "fail"
    return [
        GateCheck(
            "anchor_resolution",
            "anchors",
            status,
            detail=f"missing: {', '.join(missing)}" if missing else "",
        )
    ]


def _check_manifest(contract: HarnessContract, out_dir: Path | None) -> list[GateCheck]:
    if out_dir is None:
        return [
            GateCheck(
                "manifest_integrity",
                "artifacts",
                "unknown",
                detail="no output directory (export not run)",
            )
        ]
    manifest_path = out_dir / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entries = manifest["files"]
    except Exception as exc:
        return [
            GateCheck(
                "manifest_integrity",
                "artifacts",
                "unknown",
                detail=f"manifest unreadable: {exc}",
            )
        ]
    problems: list[str] = []
    if manifest.get("contract_sha256") != contract_sha256(contract):
        problems.append("manifest contract_sha256 mismatch")
    for entry in entries:
        path = out_dir / entry["path"]
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            problems.append(f"{entry['path']}: {exc}")
            continue
        if digest != entry["sha256"]:
            problems.append(f"{entry['path']}: sha256 mismatch")
    return [
        GateCheck(
            "manifest_integrity",
            "artifacts",
            "pass" if not problems else "fail",
            detail="; ".join(problems),
        )
    ]


def run_gates(contract: HarnessContract, out_dir: Path | None = None) -> GateReport:
    """Run every L1 check; verdict is pass iff all checks pass."""
    checks: list[GateCheck] = []
    checks.extend(_wrap("connectivity", _check_connectivity, contract))
    checks.extend(_wrap("cavity_occupancy", _check_cavity_occupancy, contract))
    checks.extend(_wrap("netlist_coverage", _check_netlist_coverage, contract))
    checks.extend(_wrap("shielding_pairing", _check_shielding_pairing, contract))
    checks.extend(_wrap("ampacity", _ampacity_details, contract))
    checks.extend(_wrap("voltage_drop", _check_voltage_drop, contract))
    checks.extend(_wrap("insulation_rating", _check_insulation_rating, contract))
    checks.extend(_wrap("bend_radius", _check_bend_radius, contract))
    checks.extend(_wrap("segregation", _check_segregation, contract))
    checks.extend(_wrap("terminal_compatibility", _check_terminal_compatibility, contract))
    checks.extend(_wrap("connector_rating", _check_connector_rating, contract))
    checks.extend(_wrap("anchor_resolution", _check_anchor_resolution, contract))
    checks.extend(_wrap("manifest_integrity", _check_manifest, contract, out_dir))
    verdict: Literal["pass", "fail"] = "pass" if all(c.status == "pass" for c in checks) else "fail"
    return GateReport(checks=checks, verdict=verdict)

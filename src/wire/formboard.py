"""Formboard layout (``*.wire-formboard.json``): routes flattened 1:1 for the harness board."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contract import HarnessContract, HarnessRoute, contract_sha256

ARTIFACT_KIND = "wire_formboard"


def route_length_mm(route: HarnessRoute) -> float:
    return sum(segment.length_m for segment in route.segments) * 1000.0


def formboard(contract: HarnessContract) -> dict[str, Any]:
    """Segment stations, anchors and the wires laid on each route, with their slack."""
    routes: list[dict[str, Any]] = []
    short: list[str] = []
    for route in sorted(contract.routes, key=lambda r: r.id):
        station = 0.0
        segments: list[dict[str, Any]] = []
        for segment in route.segments:
            end = station + segment.length_m * 1000.0
            segments.append(
                {
                    "id": segment.id,
                    "start_mm": round(station, 3),
                    "end_mm": round(end, 3),
                    "min_bend_radius_mm": segment.min_bend_radius_mm,
                }
            )
            station = end
        wires: list[dict[str, Any]] = []
        for wire in sorted(contract.wires, key=lambda w: w.id):
            if wire.route != route.id:
                continue
            slack = wire.length_m * 1000.0 - station
            if slack < 0:
                short.append(wire.id)
            wires.append(
                {
                    "id": wire.id,
                    "net": wire.net,
                    "cut_length_mm": round(wire.length_m * 1000.0, 3),
                    "slack_mm": round(slack, 3),
                }
            )
        routes.append(
            {
                "id": route.id,
                "length_mm": round(station, 3),
                "protection": route.protection,
                "anchors": list(route.anchors),
                "segments": segments,
                "wires": wires,
            }
        )
    unknown = [] if contract.routes else ["routes"]
    return {
        "artifact_kind": ARTIFACT_KIND,
        "schema_version": 1,
        "contract_id": contract.contract_id,
        "contract_sha256": contract_sha256(contract),
        "routes": routes,
        "unrouted": sorted(w.id for w in contract.wires if w.route is None),
        "short": sorted(short),
        "unknown": unknown,
        "verdict": "fail" if short or unknown else "pass",
    }


def write_formboard(contract: HarnessContract, out_dir: Path) -> dict[str, Any]:
    """Write ``<contract_id>.wire-formboard.json``; the verdict mirrors the artifact's."""
    board = formboard(contract)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{contract.contract_id}.wire-formboard.json"
    path.write_text(json.dumps(board, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "verdict": board["verdict"],
        "path": str(path),
        "short": board["short"],
        "unknown": board["unknown"],
    }

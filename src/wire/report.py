"""Design report assembly: JSON contract plus a human-readable summary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contract import HarnessContract
from .gates import GateReport


def build_report(
    contract: HarnessContract,
    gate_report: GateReport,
) -> dict[str, Any]:
    nets = contract.net_map()
    report = gate_report.to_dict(contract)
    report["schema_version"] = 1
    report["elements"] = {
        "connectors": len(contract.connectors),
        "wire_types": len(contract.wire_types),
        "nets": len(contract.nets),
        "wires": len(contract.wires),
        "routes": len(contract.routes),
        "signal_classes": sorted({net.signal_class for net in nets.values()}),
        "total_wire_length_m": round(sum(w.length_m for w in contract.wires), 4),
    }
    report["imported_sources"] = [
        {"id": s.id, "system": s.system, "ref": s.ref} for s in contract.imported_sources
    ]
    return report


def write_report(
    contract: HarnessContract,
    gate_report: GateReport,
    out_dir: Path,
) -> Path:
    report = build_report(contract, gate_report)
    path = out_dir / "design-report.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md = out_dir / "design-report.md"
    md.write_text(render_markdown(report), encoding="utf-8")
    return path


def render_markdown(report: dict[str, Any]) -> str:
    design = report["design"]
    elements = report["elements"]
    lines = [
        f"# Harness design report: {design['name']}",
        "",
        f"- contract: {design['contract_id']} / revision: {design['revision']}",
        f"- contract sha256: `{design['contract_sha256']}`",
        f"- verdict: **{report['verdict']}** "
        f"(pass {report['summary']['pass']}, fail {report['summary']['fail']}, "
        f"unknown {report['summary']['unknown']})",
        "",
        "## Elements",
        "",
        f"- connectors: {elements['connectors']} / wire types: {elements['wire_types']}"
        f" / nets: {elements['nets']} / wires: {elements['wires']}"
        f" / routes: {elements['routes']}",
        f"- signal classes: {', '.join(elements['signal_classes'])}",
        f"- total wire length: {elements['total_wire_length_m']} m",
        "",
        "## Checks",
        "",
        "| check | subject | status | measured | limit | detail |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for check in report["checks"]:
        measured = "" if check["measured"] is None else check["measured"]
        limit = "" if check["limit"] is None else check["limit"]
        lines.append(
            f"| {check['id']} | {check['subject']} | {check['status']} "
            f"| {measured} | {limit} | {check['detail']} |"
        )
    lines.append("")
    return "\n".join(lines)

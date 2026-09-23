"""wire command line interface.

Subcommands:
  doctor    probe the tool environment (JSON verdict)
  intake    validate an intake.json against a contract.json (JSON verdict)
  author    export projections, run all gates, write the report
  export    export projections without gates
  gates     re-run all gates on existing artifacts
  import    merge a connectivity or envelope source into a contract

All commands print a JSON verdict to stdout; the verdict is fail-closed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .contract import HarnessContract, load_contract
from .doctor import run_doctor
from .export import export_design
from .gates import run_gates
from .imports import (
    import_connectivity,
    import_envelope,
    load_connectivity_csv,
    load_connectivity_source,
    load_envelope_source,
)
from .intake import check_intake, load_intake
from .report import write_report


def _emit(payload: dict[str, Any]) -> int:
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("verdict") in ("pass", "ready") else 1


def cmd_doctor(_args: argparse.Namespace) -> dict[str, Any]:
    return run_doctor()


def cmd_intake(args: argparse.Namespace) -> dict[str, Any]:
    contract = load_contract(Path(args.contract))
    intake = load_intake(Path(args.intake))
    report = check_intake(contract, intake, Path(args.contract), Path(args.intake))
    return report.model_dump(mode="json")


def _load(path: str) -> HarnessContract:
    return load_contract(Path(path))


def cmd_author(args: argparse.Namespace) -> dict[str, Any]:
    out_dir = Path(args.out)
    try:
        contract = _load(args.contract)
    except Exception as exc:
        return {"verdict": "fail", "stage": "load", "detail": str(exc)}
    export_design(contract, out_dir)
    gate_report = run_gates(contract, out_dir)
    report_path = write_report(contract, gate_report, out_dir)
    result = gate_report.to_dict(contract)
    result["report_path"] = str(report_path)
    return result


def cmd_export(args: argparse.Namespace) -> dict[str, Any]:
    out_dir = Path(args.out)
    try:
        contract = _load(args.contract)
    except Exception as exc:
        return {"verdict": "fail", "stage": "load", "detail": str(exc)}
    manifest = export_design(contract, out_dir)
    return {
        "verdict": "pass",
        "design": contract.name,
        "files": [entry["path"] for entry in manifest["files"]],
    }


def cmd_gates(args: argparse.Namespace) -> dict[str, Any]:
    try:
        contract = _load(args.contract)
    except Exception as exc:
        return {"verdict": "fail", "stage": "load", "detail": str(exc)}
    gate_report = run_gates(contract, Path(args.out) if args.out else None)
    return gate_report.to_dict(contract)


def cmd_import(args: argparse.Namespace) -> dict[str, Any]:
    try:
        contract = _load(args.contract)
    except Exception as exc:
        return {"verdict": "fail", "stage": "load", "detail": str(exc)}
    source_path = Path(args.source)
    try:
        if args.kind == "circuit-json":
            merged = import_connectivity(
                contract, load_connectivity_source(source_path), source_path
            )
        elif args.kind == "csv":
            merged = import_connectivity(contract, load_connectivity_csv(source_path), source_path)
        elif args.kind == "mech-envelope":
            merged = import_envelope(contract, load_envelope_source(source_path), source_path)
        else:
            return {"verdict": "fail", "stage": "import", "detail": f"unknown kind {args.kind}"}
    except Exception as exc:
        return {"verdict": "fail", "stage": "import", "detail": str(exc)}
    out = Path(args.out) if args.out else Path(args.contract)
    out.write_text(merged.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return {
        "verdict": "pass",
        "design": merged.name,
        "imported_sources": [s.id for s in merged.imported_sources],
        "out": str(out),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wire")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor")

    p = sub.add_parser("intake")
    p.add_argument("--contract", required=True)
    p.add_argument("--intake", required=True)

    p = sub.add_parser("author")
    p.add_argument("--contract", required=True)
    p.add_argument("--out", required=True)

    p = sub.add_parser("export")
    p.add_argument("--contract", required=True)
    p.add_argument("--out", required=True)

    p = sub.add_parser("gates")
    p.add_argument("--contract", required=True)
    p.add_argument("--out", default=None)

    p = sub.add_parser("import")
    p.add_argument("--contract", required=True)
    p.add_argument("--source", required=True)
    p.add_argument(
        "--from",
        dest="kind",
        required=True,
        choices=["circuit-json", "csv", "mech-envelope"],
    )
    p.add_argument("--out", default=None)

    args = parser.parse_args(argv)
    handlers = {
        "doctor": cmd_doctor,
        "intake": cmd_intake,
        "author": cmd_author,
        "export": cmd_export,
        "gates": cmd_gates,
        "import": cmd_import,
    }
    return _emit(handlers[args.command](args))


if __name__ == "__main__":
    sys.exit(main())

"""wire command line interface.

Subcommands:
  doctor    probe the tool environment (JSON verdict)
  intake    validate an intake.json against a contract.json (JSON verdict)
  author    export projections, run all gates, write the report
  export    export projections without gates
  drawio    proxy a drawio-desktop -x export on a supported input
  drawio-lint  advisory readability lint for a drawio mxfile
  gates     re-run all gates on existing artifacts
  import    merge a connectivity or envelope source into a contract
  review-record  write a validated visual-review advisory JSON for an image

All commands print a JSON verdict to stdout; the verdict is fail-closed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

from .contract import HarnessContract, load_contract
from .doctor import run_doctor
from .export import drawio_export_formats, export_design, run_drawio_export
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


def _emit_doctor(args: argparse.Namespace) -> int:
    payload = run_doctor()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if args.warn or payload.get("verdict") in ("pass", "ready") else 1


def cmd_intake(args: argparse.Namespace) -> dict[str, Any]:
    contract = load_contract(Path(args.contract))
    intake = load_intake(Path(args.intake))
    report = check_intake(contract, intake, Path(args.contract), Path(args.intake))
    return report.model_dump(mode="json")


def _load(path: str) -> HarnessContract:
    return load_contract(Path(path))


def _drawio_formats(args: argparse.Namespace) -> list[str]:
    return [f.strip() for f in getattr(args, "drawio", "").split(",") if f.strip()]


def _apply_baseline(
    args: argparse.Namespace, result: dict[str, Any], image_path: Path
) -> dict[str, Any]:
    """Record/compare the sha256 visual baseline for a rendered image."""
    baseline_arg = getattr(args, "baseline", None)
    if not baseline_arg or not image_path.is_file():
        return result
    from .render import record_or_compare_baseline

    verdict, image_sha = record_or_compare_baseline(image_path, Path(baseline_arg))
    result["baseline"] = verdict
    result["baseline_sha256"] = image_sha
    return result


def cmd_author(args: argparse.Namespace) -> dict[str, Any]:
    out_dir = Path(args.out)
    try:
        contract = _load(args.contract)
    except Exception as exc:
        return {"verdict": "fail", "stage": "load", "detail": str(exc)}
    try:
        export_design(
            contract,
            out_dir,
            png=getattr(args, "png", False),
            drawio=_drawio_formats(args),
        )
    except (KeyError, RuntimeError) as exc:
        return {"verdict": "fail", "stage": "export", "detail": str(exc)}
    gate_report = run_gates(contract, out_dir)
    report_path = write_report(contract, gate_report, out_dir)
    result = gate_report.to_dict(contract)
    result["report_path"] = str(report_path)
    return _apply_baseline(args, result, out_dir / "harness-diagram.png")


def cmd_export(args: argparse.Namespace) -> dict[str, Any]:
    out_dir = Path(args.out)
    try:
        contract = _load(args.contract)
    except Exception as exc:
        return {"verdict": "fail", "stage": "load", "detail": str(exc)}
    try:
        manifest = export_design(
            contract,
            out_dir,
            png=getattr(args, "png", False),
            drawio=_drawio_formats(args),
        )
    except (KeyError, RuntimeError) as exc:
        return {"verdict": "fail", "stage": "export", "detail": str(exc)}
    return _apply_baseline(
        args,
        {
            "verdict": "pass",
            "design": contract.name,
            "files": [entry["path"] for entry in manifest["files"]],
        },
        out_dir / "harness-diagram.png",
    )


def cmd_drawio(args: argparse.Namespace) -> dict[str, Any]:
    try:
        result = run_drawio_export(
            Path(args.input),
            Path(args.out) if args.out else None,
            args.format,
            args.options,
        )
    except RuntimeError as exc:
        return {"verdict": "fail", "stage": "drawio", "detail": str(exc)}
    emitted = Path(result["path"])
    if emitted.suffix.lower() in {".png", ".jpg", ".jpeg"}:
        result = _apply_baseline(args, result, emitted)
    return {"verdict": "pass", **result}


def cmd_drawio_lint(args: argparse.Namespace) -> dict[str, Any]:
    from .drawio_lint import lint_file

    report = lint_file(
        Path(args.diagram),
        Path(args.out) if args.out else None,
    )
    return report.model_dump(mode="json")


def cmd_gates(args: argparse.Namespace) -> dict[str, Any]:
    try:
        contract = _load(args.contract)
    except Exception as exc:
        return {"verdict": "fail", "stage": "load", "detail": str(exc)}
    gate_report = run_gates(contract, Path(args.out) if args.out else None)
    return gate_report.to_dict(contract)


def cmd_review_record(args: argparse.Namespace) -> dict[str, Any]:
    """Write `review-visual-<slug>.advisory.json` for a reviewed image.

    The reviewer supplies impression/findings as JSON; this command binds
    them to the image bytes (sha256), validates the detail against the
    typed schema, and writes the record deterministically — instead of a
    hand-assembled JSON that could drift from `advisory.py`.
    """
    from .advisory import write_review_record

    image = Path(args.image)
    try:
        raw: Any = json.loads(Path(args.findings).read_text(encoding="utf-8"))
        raw_list = cast(list[Any], raw) if isinstance(raw, list) else None
        if raw_list is None or not all(isinstance(item, dict) for item in raw_list):
            raise ValueError("findings JSON must be a list of objects")
        findings = cast(list[dict[str, Any]], raw_list)
        impression = (
            Path(args.impression_file).read_text(encoding="utf-8").strip()
            if args.impression_file
            else (args.impression or "").strip()
        )
        path = write_review_record(
            image,
            model=args.model,
            checklist=args.checklist,
            impression=impression,
            findings=findings,
            summary=args.summary or "",
            out_dir=Path(args.out) if args.out else None,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"verdict": "fail", "stage": "review-record", "detail": str(exc)}
    return {"verdict": "pass", "record": str(path)}


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

    doctor = sub.add_parser("doctor")
    doctor.add_argument(
        "--warn",
        action="store_true",
        help="print the verdict but always exit 0 (advisory mode for hooks)",
    )

    p = sub.add_parser("intake")
    p.add_argument("--contract", required=True)
    p.add_argument("--intake", required=True)

    p = sub.add_parser("author")
    p.add_argument("--contract", required=True)
    p.add_argument("--out", required=True)
    p.add_argument(
        "--png",
        action="store_true",
        help="also write harness-diagram.png via drawio-desktop (for vision review)",
    )
    p.add_argument(
        "--drawio",
        default="",
        metavar="FORMATS",
        help=f"comma-separated drawio -x exports: {','.join(drawio_export_formats())}",
    )
    p.add_argument(
        "--baseline",
        default=None,
        metavar="BASELINE_JSON",
        help="record/compare harness-diagram.png image_sha256 against this JSON",
    )

    p = sub.add_parser("export")
    p.add_argument("--contract", required=True)
    p.add_argument("--out", required=True)
    p.add_argument(
        "--png",
        action="store_true",
        help="also write harness-diagram.png via drawio-desktop (for vision review)",
    )
    p.add_argument(
        "--drawio",
        default="",
        metavar="FORMATS",
        help=f"comma-separated drawio -x exports: {','.join(drawio_export_formats())}",
    )
    p.add_argument(
        "--baseline",
        default=None,
        metavar="BASELINE_JSON",
        help="record/compare harness-diagram.png image_sha256 against this JSON",
    )

    p = sub.add_parser("drawio")
    p.add_argument("--in", dest="input", required=True, help="input file (drawio/vsdx/csv/mermaid)")
    p.add_argument("--out", default=None)
    p.add_argument("--format", default=None)
    p.add_argument("options", nargs=argparse.REMAINDER, help="extra drawio -x flags")
    p.add_argument(
        "--baseline",
        default=None,
        metavar="BASELINE_JSON",
        help="record/compare the emitted image's sha256 against this JSON",
    )

    p = sub.add_parser(
        "drawio-lint",
        help="advisory readability lint for a drawio mxfile (never a gate verdict)",
    )
    p.add_argument("--in", dest="diagram", required=True, help="drawio mxfile to lint")
    p.add_argument("--out", default=None, help="optional report output path")

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

    p = sub.add_parser(
        "review-record",
        help="write a validated review-visual-<slug>.advisory.json for an image",
    )
    p.add_argument("--image", required=True, help="the image the review read")
    p.add_argument("--model", required=True, help="reviewer model name")
    p.add_argument(
        "--checklist",
        required=True,
        choices=["harness_diagram", "intake_image"],
    )
    p.add_argument("--impression", default=None, help="subjective reading (required)")
    p.add_argument(
        "--impression-file",
        default=None,
        help="text file with the subjective reading (alternative to --impression)",
    )
    p.add_argument(
        "--findings",
        required=True,
        help="JSON file: list of {category, severity, note, bbox?}",
    )
    p.add_argument("--summary", default=None)
    p.add_argument("--out", default=None, help="output dir (default: image dir)")

    args = parser.parse_args(argv)
    if args.command == "doctor":
        return _emit_doctor(args)
    handlers = {
        "intake": cmd_intake,
        "author": cmd_author,
        "export": cmd_export,
        "drawio": cmd_drawio,
        "drawio-lint": cmd_drawio_lint,
        "gates": cmd_gates,
        "import": cmd_import,
        "review-record": cmd_review_record,
    }
    return _emit(handlers[args.command](args))


if __name__ == "__main__":
    sys.exit(main())

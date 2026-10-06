"""Expose the wire deterministic entry points over a stdio MCP transport.

Every tool returns a JSON text payload mirroring the CLI verdicts. The
transport never judges the design itself: observations carry no pass
authority beyond what the wrapped function returns.
"""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from typing import Any

from mcp import types
from mcp.server import Server
from mcp.server.lowlevel import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

from . import __version__
from .contract import HarnessContract
from .doctor import run_doctor
from .liaison import RespondInput, inbox, respond
from .records import (
    DecisionInput,
    InsightStatusInput,
    ReadInput,
    ReconcileInput,
    SongReceiptInput,
    StageImpressionInput,
    VisionReviewInput,
    record_decision,
    record_impression,
    record_insight,
    record_read,
    record_reconcile,
    record_song_receipt,
    record_vision_review,
    records_digest,
    records_search,
    records_summary,
)
from .route_plan import ROUTE_PLAN_PNG
from .standards import CONNECTOR_FAMILIES, WIRE_SPECS
from .workspace import workspace_path

server: Server = Server(f"wire-mcp/{__version__}")

_SCHEMAS: dict[str, dict[str, Any]] = {
    "wire_record_decision": DecisionInput.model_json_schema(),
    "wire_record_impression": StageImpressionInput.model_json_schema(),
    "wire_record_vision_review": VisionReviewInput.model_json_schema(),
    "wire_record_reconcile": ReconcileInput.model_json_schema(),
    "wire_record_insight": InsightStatusInput.model_json_schema(),
    "wire_record_song_receipt": SongReceiptInput.model_json_schema(),
    "wire_record_read": ReadInput.model_json_schema(),
    "wire_records_status": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    "wire_records_digest": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    "wire_records_search": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "system": {"type": "string"},
            "kind": {"type": "string", "enum": ["stage_impression", "vision_review"]},
            "stage": {"type": "string"},
            "artifact": {"type": "string", "description": "path fragment or sha256"},
            "severity": {"type": "string", "enum": ["info", "warning", "error"]},
            "open_only": {"type": "boolean"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 200},
        },
        "additionalProperties": False,
    },
    "wire_ux_inbox": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    "wire_ux_respond": RespondInput.model_json_schema(),
    "wire_view_image": {
        "type": "object",
        "properties": {"image_path": {"type": "string"}},
        "required": ["image_path"],
        "additionalProperties": False,
    },
    "wire_doctor": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    "wire_standards": {
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "enum": ["wire_specs", "connector_families"],
            }
        },
        "required": ["kind"],
        "additionalProperties": False,
    },
    "wire_validate_contract": {
        "type": "object",
        "properties": {"contract": {"type": "object"}},
        "required": ["contract"],
        "additionalProperties": False,
    },
    "wire_intake": {
        "type": "object",
        "properties": {
            "contract_path": {"type": "string"},
            "intake_path": {"type": "string"},
        },
        "required": ["contract_path", "intake_path"],
        "additionalProperties": False,
    },
    "wire_author": {
        "type": "object",
        "properties": {
            "contract_path": {"type": "string"},
            "out_dir": {"type": "string"},
            "png": {"type": "boolean"},
            "drawio": {"type": "array", "items": {"type": "string"}},
            "baseline_path": {"type": "string"},
        },
        "required": ["contract_path", "out_dir"],
        "additionalProperties": False,
    },
    "wire_gates": {
        "type": "object",
        "properties": {
            "contract_path": {"type": "string"},
            "out_dir": {"type": "string"},
        },
        "required": ["contract_path"],
        "additionalProperties": False,
    },
    "wire_import": {
        "type": "object",
        "properties": {
            "contract_path": {"type": "string"},
            "source_path": {"type": "string"},
            "kind": {"type": "string", "enum": ["circuit-json", "csv", "mech-envelope"]},
            "out_path": {"type": "string"},
        },
        "required": ["contract_path", "source_path", "kind"],
        "additionalProperties": False,
    },
    "wire_drawio": {
        "type": "object",
        "properties": {
            "input_path": {"type": "string"},
            "output_path": {"type": "string"},
            "format": {"type": "string"},
            "options": {"type": "array", "items": {"type": "string"}},
            "baseline_path": {"type": "string"},
        },
        "required": ["input_path"],
        "additionalProperties": False,
    },
    "wire_drawio_lint": {
        "type": "object",
        "properties": {
            "diagram_path": {"type": "string"},
            "output_path": {"type": "string"},
        },
        "required": ["diagram_path"],
        "additionalProperties": False,
    },
}


def _validate_contract(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        contract = HarnessContract.model_validate(payload)
    except Exception as exc:
        return {"verdict": "fail", "stage": "schema", "detail": str(exc)}
    return {"verdict": "pass", "design": contract.name, "elements": len(contract.element_ids())}


def _text(payload: Any) -> list[types.ContentBlock]:
    return [
        types.TextContent(
            type="text", text=json.dumps(payload, indent=2, sort_keys=True, default=str)
        )
    ]


def _path_arg(value: str | None) -> str | None:
    return str(workspace_path(value)) if value is not None else None


_IMAGE_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def image_content(path: Path) -> types.ImageContent | None:
    """Attach a rendered image so vision models see it inline."""
    mime = _IMAGE_MIME.get(path.suffix.lower())
    if mime is None or not path.is_file():
        return None
    return types.ImageContent(
        type="image",
        data=base64.b64encode(path.read_bytes()).decode("ascii"),
        mimeType=mime,
    )


def tool_specs() -> list[types.Tool]:
    return [
        types.Tool(
            name=name,
            description=_DESCRIPTIONS[name],
            inputSchema=schema,
            annotations=_ANNOTATIONS[name],
        )
        for name, schema in _SCHEMAS.items()
    ]


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return tool_specs()


_DESCRIPTIONS: dict[str, str] = {
    "wire_record_decision": (
        "Record a design decision (VibeBB Record Protocol): first principles, at least two "
        "options with pros/cons, the chosen option, a rationale of 200+ chars, evidence "
        "paths (hashed) or references, assumptions, unknowns, risks, revisit trigger. "
        "Record one for every non-trivial choice without being asked."
    ),
    "wire_record_impression": (
        "Record the impression that closes a stage: 400+ chars and 3+ sentences of prose, "
        "facets (observed, works, concerns with severity/about/anchor, maker and user "
        "feelings, next_actions), 2+ claims whose anchor is an exact token in the cited "
        "artifact, optional insights (testable hypotheses for any sister) and an upstream "
        "entry (adopted/deferred/disputed/noted + effect) for every sister impression you "
        "took in. Binds the artifacts by sha256; near copies of earlier impressions fail."
    ),
    "wire_record_vision_review": (
        "Record what you thought after looking at an image: the impression body (prose, "
        "facets, claims) plus findings and a lookback that re-checks every claim against "
        "the image. reviewer is primary, blind (independent, never shown the first review) "
        "or tiebreak. Bind to image_path (hashed) or a vision tool source_event_id."
    ),
    "wire_record_reconcile": (
        "Compare independent reviews of one image deterministically: [primary, blind] "
        "(round 1) or [primary, blind, tiebreak] (round 2, the last). A round-2 split is "
        "'unresolved' and counts as unknown; reviews are never re-asked beyond that."
    ),
    "wire_record_insight": (
        "Move an impression insight (hypothesis) through tried / adopted / rejected / "
        "deferred / superseded. Adopted needs a deterministic gate pass and a decision; "
        "rejected insights cannot be proposed again without 'revisits' and new evidence."
    ),
    "wire_record_song_receipt": (
        "Receive a bard song addressed to wire (liaison/<id>.bard-song.json): what it made "
        "you feel and whether it makes you look at the design again. Songs never feed a "
        "gate, and a receipt never asks bard for another song."
    ),
    "wire_record_read": (
        "Record that you took in a sister artifact; resolves the impressions bound to its "
        "bytes or cited in it. Imports do this automatically. Answer each resolved ref in "
        "the upstream field of your next impression."
    ),
    "wire_records_digest": (
        "Family-wide impression digest across observations/*: integrity per plugin, open "
        "concerns by severity, disputes, unanswered reads, insights and their status, "
        "split vision reviews and undelivered songs."
    ),
    "wire_records_search": (
        "Search every plugin's impressions by keyword, plugin, stage, artifact path or "
        "sha256, severity and open concerns. Logs with broken integrity are listed "
        "separately and never mixed into results."
    ),
    "wire_records_status": (
        "Counts of decision / impression / vision-review records and the last Stop-hook "
        "verdict listing records this session still owes."
    ),
    "wire_ux_inbox": (
        "List UX-creator SLP v2 requests in liaison/ that target wire, each with its state "
        "(new, answered, stale, blocked) and every malformed liaison file. Check it at "
        "session start and before answering."
    ),
    "wire_ux_respond": (
        "Write liaison/<request>.ux-response.json (SLP v2). Hashes the request inputs and "
        "the delivered artifacts; derives gate verdicts from design_reports. Refuses 'done' "
        "with a fail/unknown gate, on a stale or blocked request, without artifacts or an "
        "impression ref, and any decision/impression ref missing from the VRP logs."
    ),
    "wire_view_image": (
        "Return a workspace PNG/JPEG inline so a vision-capable model sees it (renders, "
        "intake photos, sister artifacts). Record a wire_record_vision_review afterwards."
    ),
    "wire_doctor": "Probe the wire tool environment; JSON verdict.",
    "wire_standards": "Return reference wire spec or connector family tables.",
    "wire_validate_contract": "Validate a harness contract JSON against the schema.",
    "wire_intake": "Run the intake/provenance gate between contract and intake files.",
    "wire_author": (
        "Export projections (optionally drawio-desktop renders: png, jpg, pdf, html, xml), "
        "run all gates, write the design report. png defaults to true so the harness "
        "diagram (and route plan, when mech anchors carry positions) come back inline."
    ),
    "wire_gates": "Re-run all deterministic gates on existing artifacts.",
    "wire_import": (
        "Merge a connectivity or envelope source file into a contract; writes "
        "<contract-stem>.merged.contract.json next to the contract when out_path "
        "is omitted."
    ),
    "wire_drawio": (
        "Export a drawio/vsdx/csv/mermaid file through drawio-desktop -x "
        "(pdf/svg/png/jpg/xml/html; options pass any extra drawio flags "
        "such as -l, --layout, --theme, --size, -u, -p, -g, -a)."
    ),
    "wire_drawio_lint": (
        "Advisory readability lint for a drawio mxfile; JSON report, never a gate verdict."
    ),
}


def _anno(title: str, *, write: bool) -> types.ToolAnnotations:
    return types.ToolAnnotations(
        title=title,
        readOnlyHint=not write,
        destructiveHint=write,
        idempotentHint=True,
        openWorldHint=False,
    )


_ANNOTATIONS: dict[str, types.ToolAnnotations] = {
    "wire_record_decision": _anno("Record decision", write=True),
    "wire_record_impression": _anno("Record stage impression", write=True),
    "wire_record_vision_review": _anno("Record vision review", write=True),
    "wire_record_reconcile": _anno("Reconcile vision reviews", write=True),
    "wire_record_insight": _anno("Record insight status", write=True),
    "wire_record_song_receipt": _anno("Record song receipt", write=True),
    "wire_record_read": _anno("Record upstream read", write=True),
    "wire_records_status": _anno("Records status", write=False),
    "wire_records_digest": _anno("Records digest", write=False),
    "wire_records_search": _anno("Records search", write=False),
    "wire_ux_inbox": _anno("UX liaison inbox", write=False),
    "wire_ux_respond": _anno("UX liaison respond", write=True),
    "wire_view_image": _anno("View image", write=False),
    "wire_doctor": _anno("Wire doctor", write=False),
    "wire_standards": _anno("Wire standards", write=False),
    "wire_validate_contract": _anno("Validate harness contract", write=False),
    "wire_intake": _anno("Intake gate", write=False),
    "wire_author": _anno("Author harness design", write=True),
    "wire_gates": _anno("Re-run gates", write=False),
    "wire_import": _anno("Import connectivity source", write=True),
    "wire_drawio": _anno("Drawio export", write=True),
    "wire_drawio_lint": _anno("Drawio lint", write=False),
}


async def dispatch_tool(name: str, arguments: dict[str, Any]) -> list[types.ContentBlock]:
    from .cli import cmd_author, cmd_drawio, cmd_gates, cmd_import, cmd_intake

    if name == "wire_doctor":
        return _text(run_doctor())
    if name == "wire_record_decision":
        return _text(record_decision(arguments))
    if name == "wire_record_impression":
        return _text(record_impression(arguments))
    if name == "wire_record_vision_review":
        return _text(record_vision_review(arguments))
    if name == "wire_record_reconcile":
        return _text(record_reconcile(arguments))
    if name == "wire_record_insight":
        return _text(record_insight(arguments))
    if name == "wire_record_song_receipt":
        return _text(record_song_receipt(arguments))
    if name == "wire_record_read":
        return _text(record_read(arguments))
    if name == "wire_records_status":
        return _text(records_summary())
    if name == "wire_records_digest":
        return _text(records_digest())
    if name == "wire_records_search":
        return _text(records_search(arguments))
    if name == "wire_ux_inbox":
        return _text(inbox())
    if name == "wire_ux_respond":
        return _text(respond(arguments))
    if name == "wire_view_image":
        image_path = workspace_path(arguments["image_path"])
        image = image_content(image_path)
        if image is None:
            raise ValueError(f"not a readable PNG/JPEG: {arguments['image_path']}")
        return [*_text({"verdict": "pass", "image_path": str(image_path)}), image]
    if name == "wire_standards":
        kind = arguments["kind"]
        if kind == "wire_specs":
            return _text({key: vars(row) for key, row in sorted(WIRE_SPECS.items())})
        return _text(dict(sorted(CONNECTOR_FAMILIES.items())))
    if name == "wire_validate_contract":
        return _text(_validate_contract(arguments["contract"]))
    if name == "wire_intake":
        return _text(
            cmd_intake(
                _ns(
                    contract=str(workspace_path(arguments["contract_path"])),
                    intake=str(workspace_path(arguments["intake_path"])),
                )
            )
        )
    if name == "wire_author":
        contract_path = str(workspace_path(arguments["contract_path"]))
        out_dir = str(workspace_path(arguments["out_dir"]))
        result = cmd_author(
            _ns(
                contract=contract_path,
                out=out_dir,
                png=arguments.get("png", True),
                drawio=",".join(arguments.get("drawio", [])),
                baseline=_path_arg(arguments.get("baseline_path")),
            )
        )
        images: list[types.ContentBlock] = []
        shown: list[str] = []
        for raster in ("harness-diagram.png", ROUTE_PLAN_PNG):
            image = image_content(Path(out_dir) / raster)
            if image is not None:
                images.append(image)
                shown.append(str(Path(out_dir) / raster))
        result["images"] = shown
        return [*_text(result), *images]
    if name == "wire_gates":
        return _text(
            cmd_gates(
                _ns(
                    contract=str(workspace_path(arguments["contract_path"])),
                    out=_path_arg(arguments.get("out_dir")),
                )
            )
        )
    if name == "wire_import":
        contract_path = Path(workspace_path(arguments["contract_path"]))
        if arguments.get("out_path"):
            out_path = workspace_path(arguments["out_path"])
        else:
            stem = contract_path.stem.removesuffix(".contract")
            out_path = contract_path.with_name(f"{stem}.merged.contract.json")
        result = cmd_import(
            _ns(
                contract=str(contract_path),
                source=str(workspace_path(arguments["source_path"])),
                kind=arguments["kind"],
                out=str(out_path),
            )
        )
        if result.get("verdict") == "pass":
            result["merged_contract"] = json.loads(out_path.read_text(encoding="utf-8"))
            result["out_path"] = str(out_path)
        return _text(result)
    if name == "wire_drawio":
        result = cmd_drawio(
            _ns(
                input=str(workspace_path(arguments["input_path"])),
                out=_path_arg(arguments.get("output_path")),
                format=arguments.get("format"),
                options=arguments.get("options", []),
                baseline=_path_arg(arguments.get("baseline_path")),
            )
        )
        drawio_content: list[types.ContentBlock] = list(_text(result))
        emitted = result.get("path")
        if isinstance(emitted, str):
            image = image_content(Path(emitted))
            if image is not None:
                drawio_content.append(image)
        return drawio_content
    if name == "wire_drawio_lint":
        from .drawio_lint import lint_file

        report = lint_file(
            workspace_path(arguments["diagram_path"]),
            workspace_path(arguments["output_path"]) if arguments.get("output_path") else None,
        )
        return _text(report.model_dump(mode="json"))
    raise ValueError(f"unknown tool {name}")


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> types.CallToolResult:
    try:
        content = await dispatch_tool(name, arguments)
    except Exception as exc:
        return types.CallToolResult(
            content=_text({"verdict": "fail", "detail": f"{name} error: {exc}"}),
            isError=True,
        )
    return types.CallToolResult(content=content, isError=False)


def _ns(**kwargs: Any) -> Any:
    import argparse

    return argparse.Namespace(**kwargs)


async def _run() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name=f"wire-mcp/{__version__}",
                server_version=__version__,
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()

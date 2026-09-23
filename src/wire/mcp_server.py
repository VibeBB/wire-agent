"""Expose the wire deterministic entry points over a stdio MCP transport.

Every tool returns a JSON text payload mirroring the CLI verdicts. The
transport never judges the design itself: observations carry no pass
authority beyond what the wrapped function returns.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
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
from .standards import CONNECTOR_FAMILIES, WIRE_SPECS

server: Server = Server(f"wire-mcp/{__version__}")

_SCHEMAS: dict[str, dict[str, Any]] = {
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
}


def _validate_contract(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        contract = HarnessContract.model_validate(payload)
    except Exception as exc:
        return {"verdict": "fail", "stage": "schema", "detail": str(exc)}
    return {"verdict": "pass", "design": contract.name, "elements": len(contract.element_ids())}


def _text(payload: Any) -> list[types.TextContent]:
    return [
        types.TextContent(
            type="text", text=json.dumps(payload, indent=2, sort_keys=True, default=str)
        )
    ]


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name=name,
            description=_DESCRIPTIONS[name],
            inputSchema=schema,
        )
        for name, schema in _SCHEMAS.items()
    ]


_DESCRIPTIONS: dict[str, str] = {
    "wire_doctor": "Probe the wire tool environment; JSON verdict.",
    "wire_standards": "Return reference wire spec or connector family tables.",
    "wire_validate_contract": "Validate a harness contract JSON against the schema.",
    "wire_intake": "Run the intake/provenance gate between contract and intake files.",
    "wire_author": (
        "Export projections (optionally the PNG raster), run all gates, write the design report."
    ),
    "wire_gates": "Re-run all deterministic gates on existing artifacts.",
    "wire_import": "Merge a connectivity or envelope source file into a contract.",
}


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    from .cli import cmd_author, cmd_gates, cmd_import, cmd_intake

    if name == "wire_doctor":
        return _text(run_doctor())
    if name == "wire_standards":
        kind = arguments["kind"]
        if kind == "wire_specs":
            return _text({key: vars(row) for key, row in sorted(WIRE_SPECS.items())})
        return _text(dict(sorted(CONNECTOR_FAMILIES.items())))
    if name == "wire_validate_contract":
        return _text(_validate_contract(arguments["contract"]))
    if name == "wire_intake":
        return _text(
            cmd_intake(_ns(contract=arguments["contract_path"], intake=arguments["intake_path"]))
        )
    if name == "wire_author":
        return _text(
            cmd_author(
                _ns(
                    contract=arguments["contract_path"],
                    out=arguments["out_dir"],
                    png=arguments.get("png", False),
                )
            )
        )
    if name == "wire_gates":
        return _text(
            cmd_gates(_ns(contract=arguments["contract_path"], out=arguments.get("out_dir")))
        )
    if name == "wire_import":
        with tempfile.TemporaryDirectory() as tmp:
            out_path = arguments.get("out_path") or str(Path(tmp) / "merged.contract.json")
            result = cmd_import(
                _ns(
                    contract=arguments["contract_path"],
                    source=arguments["source_path"],
                    kind=arguments["kind"],
                    out=out_path,
                )
            )
            if result.get("verdict") == "pass":
                result["merged_contract"] = json.loads(Path(out_path).read_text(encoding="utf-8"))
            return _text(result)
    raise ValueError(f"unknown tool {name}")


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

"""MCP tool metadata checks."""

from __future__ import annotations

import mcp.types
from src.wire.mcp_server import tool_specs

EXPECTED = {
    "wire_doctor": False,
    "wire_standards": False,
    "wire_validate_contract": False,
    "wire_intake": False,
    "wire_author": True,
    "wire_gates": False,
    "wire_import": False,
    "wire_drawio": True,
    "wire_drawio_lint": False,
}


def test_tool_annotations() -> None:
    tools: list[mcp.types.Tool] = tool_specs()
    assert {tool.name for tool in tools} == set(EXPECTED)
    for tool in tools:
        annotations = tool.annotations
        assert annotations is not None
        assert annotations.title
        assert annotations.readOnlyHint is (not EXPECTED[tool.name])
        assert annotations.destructiveHint is EXPECTED[tool.name]
        assert annotations.idempotentHint is True
        assert annotations.openWorldHint is False

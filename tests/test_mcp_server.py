"""MCP tool metadata checks."""

from __future__ import annotations

import asyncio
import base64
import json
import shutil
from pathlib import Path
from typing import Any

import mcp.types
import pytest
from src.wire.mcp_server import dispatch_tool, image_content, tool_specs

from helpers import EXAMPLE_CONTRACT

DRAWIO_PRESENT = shutil.which("drawio") is not None and shutil.which("xvfb-run") is not None

EXPECTED = {
    "wire_doctor": False,
    "wire_standards": False,
    "wire_validate_contract": False,
    "wire_intake": False,
    "wire_author": True,
    "wire_gates": False,
    "wire_import": True,
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


def _call(name: str, args: dict[str, Any]) -> list[mcp.types.ContentBlock]:
    return asyncio.run(dispatch_tool(name, args))


def test_image_content_rejects_non_image(tmp_path: Path) -> None:
    assert image_content(tmp_path / "missing.png") is None
    svg = tmp_path / "diagram.svg"
    svg.write_bytes(b"<svg/>")
    assert image_content(svg) is None


def test_image_content_attaches_png(tmp_path: Path) -> None:
    png = tmp_path / "x.png"
    data = b"\x89PNG-fake"
    png.write_bytes(data)
    block = image_content(png)
    assert isinstance(block, mcp.types.ImageContent)
    assert block.mimeType == "image/png"
    assert base64.b64decode(block.data) == data


def test_wire_author_attaches_png(tmp_path: Path) -> None:
    if not DRAWIO_PRESENT:
        pytest.skip("drawio-desktop/xvfb not installed")
    blocks = _call(
        "wire_author",
        {"contract_path": str(EXAMPLE_CONTRACT), "out_dir": str(tmp_path), "png": True},
    )
    kinds = [type(block) for block in blocks]
    assert mcp.types.ImageContent in kinds
    assert issubclass(kinds[0], mcp.types.TextContent)


def test_wire_author_baseline_records_and_matches(tmp_path: Path) -> None:
    if not DRAWIO_PRESENT:
        pytest.skip("drawio-desktop/xvfb not installed")
    baseline = tmp_path / "baseline.json"
    args = {
        "contract_path": str(EXAMPLE_CONTRACT),
        "out_dir": str(tmp_path),
        "png": True,
        "baseline_path": str(baseline),
    }
    text = next(b for b in _call("wire_author", args) if isinstance(b, mcp.types.TextContent))
    payload = json.loads(text.text)
    assert payload["baseline"] == "recorded"
    assert baseline.is_file()

    text = next(b for b in _call("wire_author", args) if isinstance(b, mcp.types.TextContent))
    payload = json.loads(text.text)
    assert payload["baseline"] == "match"

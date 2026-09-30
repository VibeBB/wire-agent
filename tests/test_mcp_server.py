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

import wire.mcp_server as mcp_server
from helpers import EXAMPLE_CONTRACT
from wire.mcp_server import call_tool, dispatch_tool, image_content, tool_specs

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


def _call_result(name: str, args: dict[str, Any]) -> mcp.types.CallToolResult:
    async def invoke() -> mcp.types.CallToolResult:
        result = await call_tool(name, args)
        assert isinstance(result, mcp.types.CallToolResult)
        return result

    return asyncio.run(invoke())


def _payload(result: mcp.types.CallToolResult) -> dict[str, Any]:
    assert isinstance(result.content[0], mcp.types.TextContent)
    return json.loads(result.content[0].text)


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


def test_wire_author_attaches_png(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if not DRAWIO_PRESENT:
        pytest.skip("drawio-desktop/xvfb not installed")
    shutil.copyfile(EXAMPLE_CONTRACT, tmp_path / "example.contract.json")
    monkeypatch.setenv("OPENHANDS_PROJECT_DIR", str(tmp_path))
    blocks = _call(
        "wire_author",
        {"contract_path": "example.contract.json", "out_dir": "out", "png": True},
    )
    kinds = [type(block) for block in blocks]
    assert mcp.types.ImageContent in kinds
    assert issubclass(kinds[0], mcp.types.TextContent)


def test_wire_author_baseline_records_and_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if not DRAWIO_PRESENT:
        pytest.skip("drawio-desktop/xvfb not installed")
    shutil.copyfile(EXAMPLE_CONTRACT, tmp_path / "example.contract.json")
    monkeypatch.setenv("OPENHANDS_PROJECT_DIR", str(tmp_path))
    baseline = tmp_path / "baseline.json"
    args = {
        "contract_path": "example.contract.json",
        "out_dir": "out",
        "png": True,
        "baseline_path": "baseline.json",
    }
    text = next(b for b in _call("wire_author", args) if isinstance(b, mcp.types.TextContent))
    payload = json.loads(text.text)
    assert payload["baseline"] == "recorded"
    assert baseline.is_file()

    text = next(b for b in _call("wire_author", args) if isinstance(b, mcp.types.TextContent))
    payload = json.loads(text.text)
    assert payload["baseline"] == "match"


def test_unknown_tool_returns_error_result() -> None:
    result = _call_result("wire_missing", {})
    assert result.isError is True
    assert _payload(result) == {
        "verdict": "fail",
        "detail": "wire_missing error: unknown tool wire_missing",
    }


def test_raised_handler_returns_error_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def broken_dispatch(
        _name: str, _arguments: dict[str, Any]
    ) -> list[mcp.types.ContentBlock]:
        raise RuntimeError("handler failed")

    monkeypatch.setattr(mcp_server, "dispatch_tool", broken_dispatch)
    result = _call_result("wire_broken", {})
    assert result.isError is True
    assert _payload(result) == {
        "verdict": "fail",
        "detail": "wire_broken error: handler failed",
    }


def test_validation_failure_is_not_a_transport_error() -> None:
    result = _call_result("wire_validate_contract", {"contract": {}})
    assert result.isError is False
    assert _payload(result)["verdict"] == "fail"


def test_mcp_rejects_path_outside_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENHANDS_PROJECT_DIR", str(tmp_path))
    result = _call_result(
        "wire_intake",
        {"contract_path": "../outside.contract.json", "intake_path": "intake.json"},
    )
    assert result.isError is True
    assert "path is outside the workspace" in _payload(result)["detail"]


def test_mcp_accepts_relative_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENHANDS_PROJECT_DIR", str(tmp_path))
    captured: dict[str, str] = {}

    def capture_intake(arguments: Any) -> dict[str, str]:
        captured["contract"] = arguments.contract
        captured["intake"] = arguments.intake
        return {"verdict": "unknown"}

    monkeypatch.setattr("wire.cli.cmd_intake", capture_intake)
    result = _call_result(
        "wire_intake",
        {"contract_path": "fixtures/contract.json", "intake_path": "intake.json"},
    )
    assert result.isError is False
    assert captured == {
        "contract": str(tmp_path / "fixtures" / "contract.json"),
        "intake": str(tmp_path / "intake.json"),
    }

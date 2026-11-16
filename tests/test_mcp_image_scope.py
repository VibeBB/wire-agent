"""Viewing another producer's image must preserve its ownership and ancestry."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from pathlib import Path

import pytest
from mcp import types

from wire import _vrp
from wire.mcp_server import call_tool


@pytest.mark.parametrize("producer", [False, True])
def test_wire_view_image_never_claims_foreign_images(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, producer: bool
) -> None:
    monkeypatch.setenv("OPENHANDS_PROJECT_DIR", str(tmp_path))
    source = tmp_path / "original.png"
    source.write_bytes(b"original PNG fixture")
    image = tmp_path / "detail.png"
    image.write_bytes(b"derived PNG fixture")
    parent = {
        "path": str(source),
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "owner_plugin": "ux",
        "origin": "renderer",
    }
    claim = {
        "path": str(image),
        "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
        "owner_plugin": "ux",
        "origin": "derived",
        "operation": "crop",
        "parents": [parent],
    }
    if producer:
        _vrp.capture_image_delivery(
            {
                "tool_name": "ux_image_detail",
                "tool_response": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {
                                    "inline_images": [
                                        {
                                            "path": str(image),
                                            "sha256": claim["sha256"],
                                            "attached": True,
                                            "identity_status": "bound",
                                            "image_identity": claim,
                                        }
                                    ]
                                }
                            ),
                        },
                        {
                            "type": "image",
                            "data": base64.b64encode(image.read_bytes()).decode(),
                            "mimeType": "image/png",
                        },
                    ]
                },
            },
            tmp_path,
            tmp_path / "observations/ux/image-observations.jsonl",
        )
    result = asyncio.run(
        call_tool(
            None,
            types.CallToolRequestParams(
                name="wire_view_image", arguments={"image_path": "detail.png"}
            ),
        )
    )
    assert not result.is_error
    log = tmp_path / "observations/wire/image-observations.jsonl"
    assert _vrp.capture_image_delivery(
        {
            "tool_name": "wire_view_image",
            "tool_input": {"image_path": "detail.png"},
            "tool_response": result.model_dump(mode="json", by_alias=True),
        },
        tmp_path,
        log,
    )
    observation = json.loads(log.read_text(encoding="utf-8"))
    assert observation["image_path"] == str(image)
    assert observation["image_identity"] == (claim if producer else None)
    assert observation["identity_status"] == ("bound" if producer else "unknown")

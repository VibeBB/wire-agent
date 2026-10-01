from __future__ import annotations

import json
from pathlib import Path

from scripts.print_locked_image import locked_image
from scripts.update_image_digest_lock import update_lock

_ATTESTATION = "https://github.com/VibeBB/wire-agent/attestations/example"


def _update(path: Path, *, attestation: str | None = None) -> bool:
    return update_lock(
        path,
        entry="wire_tools",
        image="ghcr.io/vibebb/wire-tools",
        tag=f"{'a' * 40}-tools",
        digest=f"sha256:{'b' * 64}",
        published_at="2026-10-01T00:00:00Z",
        workflow_run="https://github.com/VibeBB/wire-agent/actions/runs/1",
        dockerfile="docker/wire-tools.Dockerfile",
        tools={"python": "Python 3.12.13"},
        attestation=attestation,
    )


def test_image_lock_records_optional_attestation(tmp_path: Path) -> None:
    lock = tmp_path / "image-digests.json"

    assert _update(lock, attestation=_ATTESTATION)
    assert not _update(lock, attestation=_ATTESTATION)

    entry = json.loads(lock.read_text(encoding="utf-8"))["wire_tools"]
    assert entry["attestation"] == _ATTESTATION
    assert locked_image(lock, "wire_tools") == (f"ghcr.io/vibebb/wire-tools@sha256:{'b' * 64}")


def test_image_lock_omits_attestation_when_not_supplied(tmp_path: Path) -> None:
    lock = tmp_path / "image-digests.json"

    assert _update(lock)

    entry = json.loads(lock.read_text(encoding="utf-8"))["wire_tools"]
    assert "attestation" not in entry

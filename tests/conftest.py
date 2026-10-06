from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolated_workspace(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep VRP writes (e.g. import read receipts) out of the repository checkout.

    Hook tests resolve the workspace from the payload, so they keep the real
    environment.
    """
    if request.path.name == "test_hooks.py":
        return
    monkeypatch.setenv("OPENHANDS_PROJECT_DIR", str(tmp_path))

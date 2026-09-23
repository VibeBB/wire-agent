"""Shared test helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_CONTRACT = REPO_ROOT / "examples" / "sensor-harness" / "sensor-harness.contract.json"
EXAMPLE_INTAKE = REPO_ROOT / "examples" / "sensor-harness" / "sensor-harness.intake.json"


def example_contract_data() -> dict[str, Any]:
    return json.loads(EXAMPLE_CONTRACT.read_text(encoding="utf-8"))


def example_intake_data() -> dict[str, Any]:
    return json.loads(EXAMPLE_INTAKE.read_text(encoding="utf-8"))

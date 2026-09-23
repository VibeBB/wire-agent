"""Environment doctor: probe the tools the pipeline depends on.

Every check reports "pass" (capability present) or "fail" (missing/broken).
The verdict is fail-closed: any failed capability fails the report.
"""

from __future__ import annotations

import importlib
import platform
import sys
from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class DoctorCheck:
    capability: str
    status: Literal["pass", "fail"]
    detail: str


def _probe_module(name: str, attr: str | None = None) -> DoctorCheck:
    try:
        module = importlib.import_module(name)
    except Exception as exc:
        return DoctorCheck(name, "fail", f"import failed: {exc}")
    version = getattr(module, "__version__", "unknown")
    if attr is not None and not hasattr(module, attr):
        return DoctorCheck(name, "fail", f"missing attribute {attr}")
    return DoctorCheck(name, "pass", f"version {version}")


def _probe_python() -> DoctorCheck:
    version = sys.version_info
    ok = (version.major, version.minor) >= (3, 12)
    return DoctorCheck(
        "python",
        "pass" if ok else "fail",
        f"{platform.python_version()} (>=3.12 required)",
    )


def _probe_contract_roundtrip() -> DoctorCheck:
    try:
        from .contract import HarnessContract

        contract = HarnessContract(
            contract_id="WH-probe",
            name="probe",
            revision="r1",
        )
        contract.model_validate(contract.model_dump())
        return DoctorCheck("contract-roundtrip", "pass", "schema round-trip ok")
    except Exception as exc:
        return DoctorCheck("contract-roundtrip", "fail", f"probe failed: {exc}")


def run_doctor() -> dict[str, Any]:
    checks = [
        _probe_python(),
        _probe_module("pydantic"),
        _probe_module("mcp"),
        _probe_contract_roundtrip(),
    ]
    verdict: Literal["pass", "fail"] = "pass" if all(c.status == "pass" for c in checks) else "fail"
    return {
        "schema_version": 1,
        "verdict": verdict,
        "checks": [
            {"capability": c.capability, "status": c.status, "detail": c.detail} for c in checks
        ],
    }

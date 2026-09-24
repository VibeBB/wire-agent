#!/usr/bin/env python3
"""Deterministic authoring entry point.

``python scripts/e2e_authoring.py --contract design.contract.json --out out/x``
runs the whole pipeline: contract validation -> export -> gates ->
design report, then prints the gate verdict JSON on stdout. Exit code is 0
only when every gate passes; any failure is fail-closed (exit 2).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", required=True, help="contract JSON path")
    parser.add_argument("--out", required=True, help="output directory")
    args = parser.parse_args(argv)

    from wire.contract import load_contract
    from wire.export import export_design
    from wire.gates import run_gates
    from wire.report import write_report

    out_dir = Path(args.out)
    try:
        contract = load_contract(Path(args.contract))
    except Exception as exc:
        print(
            json.dumps(
                {"verdict": "fail", "stage": "contract", "detail": str(exc)},
                indent=2,
            )
        )
        return 2

    renders: list[str] = []
    render_status = "ok"
    try:
        export_design(contract, out_dir, png=True)
        png_path = out_dir / "harness-diagram.png"
        if png_path.is_file():
            renders.append(str(png_path))
    except RuntimeError as exc:
        # drawio-desktop unavailable — the vision lane degrades, never blocks.
        render_status = f"skipped: {exc}"
        export_design(contract, out_dir)
    report = run_gates(contract, out_dir)
    report_path = write_report(contract, report, out_dir)
    payload = report.to_dict(contract)
    payload["report_path"] = str(report_path)
    payload["renders"] = renders
    payload["render_status"] = render_status
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if report.verdict == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Opt-in smoke check: drawio-desktop renders the generated mxfile.

Runs ``wire export --drawio png,pdf,xml`` on the example contract and asserts
the canonical artifacts exist and are well-formed — proof that drawio itself
loads the mxfile we generate (stronger than self-asserted XML validity).

Usage: ``uv run python scripts/check_drawio_export.py`` (needs drawio-desktop
and xvfb on PATH, e.g. the wire-tools image).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples/sensor-harness/sensor-harness.contract.json"


def main() -> int:
    failures: list[str] = []
    if shutil.which("drawio") is None or shutil.which("xvfb-run") is None:
        print("SKIP: drawio-desktop/xvfb not installed (wire-tools image provides them)")
        return 0
    with tempfile.TemporaryDirectory(prefix="wire-drawio-check-") as tmp:
        out = Path(tmp) / "out"
        result = subprocess.run(
            [
                "uv",
                "run",
                "python",
                "-m",
                "wire",
                "export",
                "--contract",
                str(EXAMPLE),
                "--out",
                str(out),
                "--drawio",
                "png,pdf,xml",
            ],
            capture_output=True,
            check=False,
            cwd=ROOT,
        )
        payload = json.loads(result.stdout)
        if result.returncode != 0 or payload.get("verdict") != "pass":
            failures.append(f"export --drawio failed: {result.stderr.decode().strip()}")
        else:
            png = out / "harness-diagram.png"
            if not png.read_bytes().startswith(b"\x89PNG"):
                failures.append("harness-diagram.png missing or not a PNG")
            pdf = out / "harness-diagram.pdf"
            if not pdf.read_bytes().startswith(b"%PDF"):
                failures.append("harness-diagram.pdf missing or not a PDF")
            drawio_xml = out / "harness-diagram.drawio"
            if ET.parse(drawio_xml).getroot().tag != "mxfile":
                failures.append("harness-diagram.drawio missing or not an mxfile")
            svg = out / "harness-diagram.drawio.svg"
            text = svg.read_text(encoding="utf-8")
            if 'content="&lt;mxfile' not in text:
                failures.append(".drawio.svg lacks a drawio-embedded model")
            if (out / "manifest.json").exists() is False:
                failures.append("manifest.json missing")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("drawio export check passed: drawio-desktop renders the generated mxfile")
    return 0


if __name__ == "__main__":
    sys.exit(main())

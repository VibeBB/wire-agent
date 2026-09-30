from __future__ import annotations

import functools
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

__all__ = [
    "_DRAWIO_EXPORTS",
    "_DRAWIO_SUBPROCESS_TIMEOUT",
    "_DRAWIO_TIMEOUT_SECONDS",
    "_drawio_cli",
    "_drawio_export_prefix",
    "_drawio_render",
    "_drawio_supports_timeout",
    "drawio_export_formats",
    "run_drawio_export",
]


def _drawio_cli() -> list[str]:
    """Headless drawio-desktop export prefix; fails closed when unavailable."""
    if shutil.which("drawio") is None or shutil.which("xvfb-run") is None:
        raise RuntimeError(
            "drawio export needs drawio-desktop and xvfb (both ship in the wire-tools image)"
        )
    return [
        "xvfb-run",
        "-a",
        "drawio",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--disable-update",
    ]


# Per-file export budget handed to drawio-desktop 31.5.2's ``--timeout``
# (the flag fails an export exceeding it and exits 1). The subprocess bound
# adds slack so a stuck Electron boot also terminates instead of hanging.
_DRAWIO_TIMEOUT_SECONDS = 300
_DRAWIO_SUBPROCESS_TIMEOUT = _DRAWIO_TIMEOUT_SECONDS + 120


@functools.lru_cache(maxsize=1)
def _drawio_supports_timeout() -> bool:
    """Probe the installed drawio for the ``--timeout`` export flag.

    drawio-desktop 31.5.2 added ``--timeout``; older pinned images would
    treat the seconds value as an input file and fail the export. Probe
    ``--help`` through the same xvfb wrapper the export uses so detection
    only runs where the export itself can run, and cache the answer.
    """
    try:
        probe = subprocess.run(
            ["xvfb-run", "-a", "drawio", "--no-sandbox", "--help"],
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    out = probe.stdout.decode("utf-8", errors="replace")
    return probe.returncode == 0 and "--timeout" in out


def _drawio_export_prefix() -> list[str]:
    """``drawio -x`` prefix, adding ``--timeout`` only where supported."""
    prefix = ["-x"]
    if _drawio_supports_timeout():
        prefix += ["--timeout", str(_DRAWIO_TIMEOUT_SECONDS)]
    return prefix


def _drawio_render(mxfile: str, fmt_args: Sequence[str]) -> bytes:
    """Render the mxfile through ``drawio -x`` and return the output bytes.

    drawio-desktop renders the canonical view (what diagrams.net shows) and
    resolves CJK glyphs through its bundled text stack — a successful run
    also proves drawio actually loads the generated model. The subprocess
    boundary keeps the Electron app out of the import set. Output bytes vary
    with the installed drawio version, so rendered artifacts are review aids
    rather than byte-stable projections.
    """
    cmd = _drawio_cli()
    with tempfile.TemporaryDirectory(prefix="wire-drawio-") as tmp:
        src = Path(tmp) / "harness.drawio"
        out = Path(tmp) / "out"
        src.write_text(mxfile, encoding="utf-8")
        try:
            result = subprocess.run(
                [
                    *cmd,
                    *_drawio_export_prefix(),
                    *fmt_args,
                    "-o",
                    str(out),
                    str(src),
                ],
                capture_output=True,
                check=False,
                timeout=_DRAWIO_SUBPROCESS_TIMEOUT,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"drawio -x {' '.join(fmt_args)} timed out after {_DRAWIO_SUBPROCESS_TIMEOUT}s"
            ) from exc
        if result.returncode != 0 or not out.is_file() or out.stat().st_size == 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"drawio -x {' '.join(fmt_args)} failed: {detail}")
        return out.read_bytes()


_DRAWIO_EXPORTS: dict[str, tuple[str, list[str]]] = {
    "png": ("harness-diagram.png", ["-f", "png", "-s", "2"]),
    "jpg": ("harness-diagram.jpg", ["-f", "jpg", "-s", "2", "-q", "95"]),
    "pdf": ("harness-diagram.pdf", ["-f", "pdf", "--crop"]),
    "html": ("harness-diagram.html", ["-f", "html", "-a"]),
    "svg": ("harness-diagram.svg", ["-f", "svg"]),
    "xml": ("harness-diagram.drawio", ["-f", "xml"]),
}


def drawio_export_formats() -> list[str]:
    """Formats accepted by ``--drawio`` (drawio-desktop -x outputs)."""
    return sorted(_DRAWIO_EXPORTS)


def run_drawio_export(
    input_path: Path,
    output_path: Path | None,
    fmt: str | None,
    options: Sequence[str],
) -> dict[str, Any]:
    """Proxy a drawio-desktop ``-x`` export on any supported input.

    ``options`` passes through drawio flags (pages, layers, layout, embeds,
    quality, ...) so the full CLI surface is reachable; inputs may be drawio,
    vsdx, csv, or mermaid files.
    """
    cmd = _drawio_cli()
    argv = [*cmd, *_drawio_export_prefix()]
    if fmt is not None:
        argv += ["-f", fmt]
    if output_path is not None:
        argv += ["-o", str(output_path)]
    argv += [*options, str(input_path)]
    try:
        result = subprocess.run(
            argv, capture_output=True, check=False, timeout=_DRAWIO_SUBPROCESS_TIMEOUT
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"drawio -x timed out after {_DRAWIO_SUBPROCESS_TIMEOUT}s") from exc
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"drawio -x failed: {detail}")
    emitted = output_path or input_path.with_suffix(f".{fmt or 'pdf'}")
    return {"path": str(emitted), "exists": emitted.is_file()}

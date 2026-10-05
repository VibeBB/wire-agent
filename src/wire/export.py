"""Deterministic artifact export.

Writes wire-list.csv, cut-table.csv, bom.json, bom.csv, and
harness-diagram.drawio.svg (an SVG whose root `content` attribute embeds
the editable drawio model), route-plan.drawio.svg when imported mech
anchors carry positions, plus manifest.json (sha256 per file) and
provenance.json (contract hash and tool versions). Nothing here judges
the design; gates read these artifacts. Identical contract bytes produce
identical artifact bytes.
"""

from __future__ import annotations

import hashlib
import json
import platform
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import __version__, drawio_lint
from .contract import HarnessContract, contract_sha256
from .diagram import _BORDER_LEFT_MM as _BORDER_LEFT_MM
from .diagram import _BORDER_MM as _BORDER_MM
from .diagram import SVG_NS as SVG_NS
from .diagram import _frame_geometry as _frame_geometry
from .diagram import _harness_mxfile as _harness_mxfile
from .diagram import _mm as _mm
from .diagram import _net_label as _net_label
from .diagram import _wire_label as _wire_label
from .diagram import _zone_spans as _zone_spans
from .drawio_cli import _DRAWIO_EXPORTS as _DRAWIO_EXPORTS
from .drawio_cli import _DRAWIO_SUBPROCESS_TIMEOUT as _DRAWIO_SUBPROCESS_TIMEOUT
from .drawio_cli import _DRAWIO_TIMEOUT_SECONDS as _DRAWIO_TIMEOUT_SECONDS
from .drawio_cli import _drawio_cli as _drawio_cli
from .drawio_cli import _drawio_export_prefix as _drawio_export_prefix
from .drawio_cli import _drawio_render as _drawio_render
from .drawio_cli import _drawio_supports_timeout as _drawio_supports_timeout
from .drawio_cli import drawio_export_formats as drawio_export_formats
from .drawio_cli import run_drawio_export as run_drawio_export
from .export_tables import _bom as _bom
from .export_tables import _bom_csv as _bom_csv
from .export_tables import _csv_text as _csv_text
from .export_tables import _cut_table_csv as _cut_table_csv
from .export_tables import _wire_list_csv as _wire_list_csv
from .route_plan import ROUTE_PLAN_NAME, ROUTE_PLAN_PNG, route_plan_mxfile


def export_design(
    contract: HarnessContract,
    out_dir: Path,
    *,
    png: bool = False,
    drawio: Sequence[str] = (),
) -> dict[str, Any]:
    """Write every projection plus manifest.json and provenance.json.

    The diagram is rendered by drawio-desktop (canonical rendering,
    embedded model round-trips); it ships in the wire-tools image, and a
    missing drawio/xvfb fails the export rather than degrading the artifact.
    ``png=True`` is a shorthand for ``drawio=["png"]`` — ``drawio`` lists
    extra formats (png, jpg, pdf, html, xml) rendered through ``drawio -x``
    for vision-capable reviewers (the OpenHands FileEditorTool auto-sends
    raster images to the LLM).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    mxfile = _harness_mxfile(contract)
    artifacts: dict[str, str] = {
        "wire-list.csv": _wire_list_csv(contract),
        "cut-table.csv": _cut_table_csv(contract),
        "bom.csv": _bom_csv(contract),
    }
    artifacts["harness-diagram.drawio.svg"] = _drawio_render(mxfile, ["-f", "svg", "-e"]).decode(
        "utf-8"
    )
    bom_json = json.dumps(_bom(contract), indent=2, sort_keys=True) + "\n"
    artifacts["bom.json"] = bom_json

    files: list[dict[str, Any]] = []
    for name in sorted(artifacts):
        path = out_dir / name
        path.write_text(artifacts[name], encoding="utf-8")
        files.append(
            {
                "path": name,
                "sha256": hashlib.sha256(artifacts[name].encode("utf-8")).hexdigest(),
                "bytes": len(artifacts[name].encode("utf-8")),
            }
        )

    lint_report = drawio_lint.lint_text(mxfile, source=Path("harness-diagram.drawio"))
    lint_text_out = lint_report.model_dump_json(indent=2) + "\n"
    (out_dir / "harness-diagram.drawio_lint.json").write_text(lint_text_out, encoding="utf-8")
    files.append(
        {
            "path": "harness-diagram.drawio_lint.json",
            "sha256": hashlib.sha256(lint_text_out.encode("utf-8")).hexdigest(),
            "bytes": len(lint_text_out.encode("utf-8")),
        }
    )

    extra = set(drawio)
    if png:
        extra.add("png")
    for fmt in sorted(extra):
        name, fmt_args = _DRAWIO_EXPORTS[fmt]
        rendered = _drawio_render(mxfile, fmt_args)
        path = out_dir / name
        path.write_bytes(rendered)
        files.append(
            {
                "path": name,
                "sha256": hashlib.sha256(rendered).hexdigest(),
                "bytes": len(rendered),
            }
        )

    plan = route_plan_mxfile(contract)
    if plan is not None:
        renders: list[tuple[str, list[str]]] = [(ROUTE_PLAN_NAME, ["-f", "svg", "-e"])]
        if "png" in extra:
            renders.append((ROUTE_PLAN_PNG, ["-f", "png", "-s", "2"]))
        for name, fmt_args in renders:
            rendered = _drawio_render(plan, fmt_args)
            (out_dir / name).write_bytes(rendered)
            files.append(
                {
                    "path": name,
                    "sha256": hashlib.sha256(rendered).hexdigest(),
                    "bytes": len(rendered),
                }
            )

    provenance = {
        "schema_version": 1,
        "license": "BSD-3-Clause",
        "generator": f"wire-agent/{__version__}",
        "contract": contract.name,
        "contract_id": contract.contract_id,
        "revision": contract.revision,
        "contract_sha256": contract_sha256(contract),
        "imported_sources": [
            {
                "id": s.id,
                "system": s.system,
                "ref": s.ref,
                "sha256": s.sha256,
            }
            for s in contract.imported_sources
        ],
        "tool_versions": {"python": platform.python_version()},
        "diagram_renderer": "drawio-desktop",
    }
    provenance_text = json.dumps(provenance, indent=2, sort_keys=True) + "\n"
    (out_dir / "provenance.json").write_text(provenance_text, encoding="utf-8")
    files.append(
        {
            "path": "provenance.json",
            "sha256": hashlib.sha256(provenance_text.encode("utf-8")).hexdigest(),
            "bytes": len(provenance_text.encode("utf-8")),
        }
    )
    manifest = {
        "schema_version": 1,
        "contract_sha256": contract_sha256(contract),
        "files": files,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest

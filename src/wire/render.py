"""sha256 visual baseline for rendered harness diagrams.

Rendered images (drawio-desktop `harness-diagram.png`/`jpg` exports and
`wire_drawio` outputs) are advisory projections: their bytes vary with the
installed drawio version, so they are never byte-stable projections. A
sha256 baseline still answers "did the rendered diagram change since the
last revision?" as a closed question — a deterministic regression signal
for the L2 vision lane without any image diffing. A missing baseline file
records `{image, image_sha256, recorded_at}`; an existing one reports
`match`/`diff`.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

BaselineVerdict = Literal["match", "diff", "recorded"]


class RenderBaselineError(RuntimeError):
    """Raised when a baseline cannot be recorded or compared."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record_or_compare_baseline(
    image_path: Path, baseline_path: Path
) -> tuple[BaselineVerdict, str]:
    """Write or compare a sha256 visual baseline for `image_path`.

    Returns ``(verdict, image_sha256)``. A missing baseline file records
    the current hash and yields ``recorded``; an existing one yields
    ``match`` or ``diff``. Unreadable inputs fail closed.
    """
    if not image_path.is_file():
        raise RenderBaselineError(f"image missing: {image_path}")
    image_sha = _sha256(image_path)
    if not baseline_path.is_file():
        record = {
            "image": str(image_path),
            "image_sha256": image_sha,
            "recorded_at": datetime.now(UTC).isoformat(),
        }
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return "recorded", image_sha
    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        recorded_sha = baseline["image_sha256"]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError) as exc:
        raise RenderBaselineError(f"cannot read baseline {baseline_path}: {exc}") from exc
    if not isinstance(recorded_sha, str):
        raise RenderBaselineError(
            f"cannot read baseline {baseline_path}: image_sha256 is not a string"
        )
    return ("match" if recorded_sha == image_sha else "diff"), image_sha

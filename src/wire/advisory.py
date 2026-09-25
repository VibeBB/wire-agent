"""Typed advisory review records (L2 only — never verdicts).

A vision-capable reviewer writes `review-visual-<slug>.advisory.json`
next to `design-report.json`; `parse_visual_review` validates the detail
so a malformed model answer can never masquerade as a record (returns
`None`). Same contract shape as circuit's `src/circuit/advisory.py` and
mech's `src/mech/advisory.py`.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

VISION_REVIEW_TOOL = "vision_review"
IMPRESSION_MIN_LENGTH = 240
_SENTENCE_MARKS = "。.!?"

VisualChecklist = Literal["harness_diagram", "intake_image"]
VisualFindingCategory = Literal[
    "missing_connection",
    "wrong_connector",
    "routing_anomaly",
    "label_collision",
    "text_outside_frame",
    "dimension_legibility",
    "ambiguous_notation",
    "missing_dimension",
    "missing_manufacturing_info",
    "design_intent",
    "datasheet_mismatch",
    "other",
]


class VisualFinding(BaseModel):
    """One visual-review finding, optionally localized by a bounding box."""

    model_config = ConfigDict(extra="forbid")

    category: VisualFindingCategory
    severity: Literal["error", "warning", "info"]
    note: str
    bbox: list[float] | None = Field(
        default=None,
        description="normalized [x, y, w, h] against the reviewed image",
    )


class VisualReviewDetail(BaseModel):
    """Typed detail for a `vision_review` advisory record."""

    model_config = ConfigDict(extra="forbid")

    image_path: str
    image_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model: str
    checklist: VisualChecklist
    impression: str = Field(
        min_length=IMPRESSION_MIN_LENGTH,
        description=(
            "Subjective impression from reading the drawing; required and "
            "multi-sentence — a terse line is rejected at validation time"
        ),
    )
    findings: list[VisualFinding] = Field(default_factory=lambda: list[VisualFinding]())

    @field_validator("impression")
    @classmethod
    def _impression_is_prose(cls, value: str) -> str:
        if sum(value.count(mark) for mark in _SENTENCE_MARKS) < 2:
            raise ValueError("impression must be a multi-sentence reading")
        return value


class AdvisoryResult(BaseModel):
    """Generic advisory-lane envelope shared by review-side tool results."""

    model_config = ConfigDict(extra="forbid")

    tool: str
    stage: Literal["intake", "brief", "author", "gates", "review", "export"]
    status: Literal["ok", "error", "not_applicable"]
    summary: str = ""
    artifacts: list[str] = Field(default_factory=list)
    detail: dict[str, Any] = Field(default_factory=dict)


def parse_visual_review(result: AdvisoryResult) -> VisualReviewDetail | None:
    """Validate `result.detail` as a VisualReviewDetail when tool is vision_review."""
    if result.tool != VISION_REVIEW_TOOL:
        return None
    try:
        return VisualReviewDetail.model_validate(result.detail)
    except ValidationError:
        return None


def review_record_path(image_path: Path, out_dir: Path | None = None) -> Path:
    """`review-visual-<slug>.advisory.json` next to the image (or out_dir)."""
    slug = re.sub(r"[^a-z0-9]+", "-", image_path.stem.lower()).strip("-") or "image"
    directory = out_dir if out_dir is not None else image_path.parent
    return directory / f"review-visual-{slug}.advisory.json"


def build_review_record(
    image_path: Path,
    *,
    model: str,
    checklist: VisualChecklist,
    impression: str,
    findings: list[dict[str, Any]],
    summary: str = "",
) -> AdvisoryResult:
    """Build the typed `vision_review` advisory record for one image.

    The image sha256 is computed here so the record always binds the
    judgment to the exact bytes reviewed; the detail is validated with
    the same schema `parse_visual_review` enforces, so a bad payload
    raises instead of producing a malformed record.
    """
    sha256 = hashlib.sha256(image_path.read_bytes()).hexdigest()
    detail = VisualReviewDetail(
        image_path=str(image_path),
        image_sha256=sha256,
        model=model,
        checklist=checklist,
        impression=impression,
        findings=[VisualFinding.model_validate(f) for f in findings],
    )
    return AdvisoryResult(
        tool=VISION_REVIEW_TOOL,
        stage="review",
        status="ok",
        summary=summary or f"visual review of {image_path.name}",
        artifacts=[str(image_path)],
        detail=detail.model_dump(mode="json"),
    )


def write_review_record(
    image_path: Path,
    *,
    model: str,
    checklist: VisualChecklist,
    impression: str,
    findings: list[dict[str, Any]],
    summary: str = "",
    out_dir: Path | None = None,
) -> Path:
    """Validate and write `review-visual-<slug>.advisory.json`; returns it."""
    record = build_review_record(
        image_path,
        model=model,
        checklist=checklist,
        impression=impression,
        findings=findings,
        summary=summary,
    )
    path = review_record_path(image_path, out_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(record.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path

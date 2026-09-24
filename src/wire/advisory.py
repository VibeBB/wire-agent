"""Typed advisory review records (L2 only — never verdicts).

A vision-capable reviewer writes `review-visual-<slug>.advisory.json`
next to `design-report.json`; `parse_visual_review` validates the detail
so a malformed model answer can never masquerade as a record (returns
`None`). Same contract shape as circuit's `src/circuit/advisory.py` and
mech's `src/mech/advisory.py`.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

VISION_REVIEW_TOOL = "vision_review"

VisualChecklist = Literal["harness_diagram", "intake_image"]
VisualFindingCategory = Literal[
    "missing_connection",
    "wrong_connector",
    "routing_anomaly",
    "label_collision",
    "text_outside_frame",
    "dimension_legibility",
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
    findings: list[VisualFinding] = Field(default_factory=lambda: list[VisualFinding]())


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

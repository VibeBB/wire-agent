"""Intake/provenance sidecar for the harness contract.

Every contract element is bound to a source id: a user-stated requirement
(R*), a declared assumption (A*), an open question (Q*), or an imported
contract source (I*). Elements with no user requirement behind them must be
either imported or explicitly assumed — nothing may exist for no reason.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .contract import HarnessContract, contract_sha256


class Requirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^R[0-9]+$")
    text: str = Field(min_length=1)
    source: Literal["user", "agent"]
    speaker: str = Field(min_length=1)


class EvidenceRef(BaseModel):
    """Provenance binding to an intake evidence file (image, document, CAD file).

    `path` resolves relative to the intake file's directory when not absolute.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["image", "document", "cad_file"]
    path: Path
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    note: str = Field(default="")


class Assumption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^A[0-9]+$")
    text: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    evidence: EvidenceRef | None = None


class OpenQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^Q[0-9]+$")
    text: str = Field(min_length=1)
    evidence: EvidenceRef | None = None


class Intake(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    requirements: list[Requirement] = Field(min_length=1)
    assumptions: list[Assumption] = Field(default_factory=list[Assumption])
    open_questions: list[OpenQuestion] = Field(default_factory=list[OpenQuestion])
    element_sources: dict[str, list[str]] = Field(default_factory=dict[str, list[str]])

    @model_validator(mode="after")
    def validate_sources(self) -> Intake:
        for key, sources in self.element_sources.items():
            if not sources:
                raise ValueError(f"element_sources[{key}] must not be empty")
        return self


class IntakeReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_path: Path
    intake_path: Path
    contract_sha256: str
    intake_sha256: str
    sha_matches: bool
    unmapped_elements: list[str]
    unknown_elements: list[str]
    unknown_sources: dict[str, list[str]]
    assumption_only_elements: list[str]
    open_questions: list[OpenQuestion]
    evidence_errors: list[str]
    verdict: Literal["ready", "blocked"]
    reasons: list[str]


def load_intake(path: Path) -> Intake:
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not load intake {path}: {exc}") from exc
    return Intake.model_validate(value)


def intake_sha256(intake: Intake) -> str:
    return hashlib.sha256(intake.model_dump_json().encode("utf-8")).hexdigest()


def check_intake(
    contract: HarnessContract,
    intake: Intake,
    contract_path: Path,
    intake_path: Path,
) -> IntakeReport:
    """Fail-closed provenance gate between the contract and its sidecar."""
    expected = contract_sha256(contract)
    sha_matches = intake.contract_sha256 == expected

    element_ids = contract.element_ids()
    imported_ids = {source.id for source in contract.imported_sources}
    source_ids = (
        {r.id for r in intake.requirements}
        | {a.id for a in intake.assumptions}
        | {q.id for q in intake.open_questions}
        | imported_ids
    )

    unmapped = [e for e in element_ids if e not in intake.element_sources]
    unknown_elements = [e for e in intake.element_sources if e not in element_ids]

    unknown_sources: dict[str, list[str]] = {}
    for key, sources in intake.element_sources.items():
        missing = [s for s in sources if s not in source_ids]
        if missing:
            unknown_sources[f"element_sources.{key}"] = missing

    assumption_ids = {a.id for a in intake.assumptions}
    question_ids = {q.id for q in intake.open_questions}
    requirement_ids = {r.id for r in intake.requirements}
    non_req = assumption_ids | question_ids

    assumption_only = [
        element
        for element, sources in intake.element_sources.items()
        if element in element_ids
        and bool(sources)
        and not any(s in requirement_ids for s in sources)
        and any(s in non_req for s in sources)
        and not any(s in imported_ids for s in sources)
    ]

    reasons: list[str] = []
    if not sha_matches:
        reasons.append("contract_sha256 mismatch: contract was edited after intake")
    if unmapped:
        reasons.append(f"unmapped elements: {', '.join(sorted(unmapped))}")
    if unknown_elements:
        reasons.append(f"element_sources references unknown elements: {sorted(unknown_elements)}")
    if unknown_sources:
        reasons.append(f"unknown source ids: {unknown_sources}")
    if assumption_only:
        reasons.append(f"elements backed only by assumptions/questions: {sorted(assumption_only)}")
    if intake.open_questions:
        reasons.append(f"open questions: {', '.join(q.id for q in intake.open_questions)}")
    evidence_errors = check_evidence(intake, intake_path=intake_path)
    reasons.extend(evidence_errors)

    verdict: Literal["ready", "blocked"] = "ready" if not reasons else "blocked"
    return IntakeReport(
        contract_path=contract_path,
        intake_path=intake_path,
        contract_sha256=expected,
        intake_sha256=intake_sha256(intake),
        sha_matches=sha_matches,
        unmapped_elements=sorted(unmapped),
        unknown_elements=sorted(unknown_elements),
        unknown_sources=unknown_sources,
        assumption_only_elements=sorted(assumption_only),
        open_questions=intake.open_questions,
        evidence_errors=evidence_errors,
        verdict=verdict,
        reasons=reasons,
    )


def check_evidence(intake: Intake, *, intake_path: Path) -> list[str]:
    """Verify every declared evidence file exists and matches its sha256."""
    errors: list[str] = []
    base = intake_path.resolve().parent
    for record in [*intake.assumptions, *intake.open_questions]:
        evidence = record.evidence
        if evidence is None:
            continue
        path = evidence.path if evidence.path.is_absolute() else base / evidence.path
        label = f"{record.id} evidence {evidence.path}"
        try:
            data = path.read_bytes()
        except OSError:
            errors.append(f"{label}: file missing")
            continue
        if hashlib.sha256(data).hexdigest() != evidence.sha256:
            errors.append(f"{label}: sha256 mismatch")
    return errors

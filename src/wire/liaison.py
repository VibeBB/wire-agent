"""Sister Liaison Protocol (SLP) v2 — wire's side of the UX-creator liaison.

UX-creator writes `liaison/<id>.ux-request.json`; wire answers with
`liaison/<id>.ux-response.json` beside it. These models are a strict local
mirror of the v2 schema (no import of UX-creator code, ADR-0003):

* `inbox` lists the requests that target `wire`, validates them and
  reports a `state` per request — `new`, `answered`, `stale` (an input's
  current sha256 differs from the request, or from the hashes the
  response saw) or `blocked` (a `depends_on` request is unanswered) —
  plus every malformed file.
* `respond` writes the response, hashing the inputs it saw and the
  artifacts it delivers, and refuses a response that would misreport:
  `done` while a gate verdict is `fail`/`unknown`, `done` on a blocked or
  stale request, or decision/impression references that do not exist in
  wire's VibeBB Record Protocol logs.

Liaison files are coordination evidence; they never change a gate verdict.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from . import _vrp
from .records import LOG_FILES, records_dir, sha256_file, tree_sha256
from .workspace import workspace_path, workspace_root

PLUGIN: Final = "wire"
SCHEMA_VERSION: Final = 2
SYSTEM: Final = "ux-creator"
LIAISON_DIR: Final = Path("liaison")
REQUEST_SUFFIX: Final = ".ux-request.json"
RESPONSE_SUFFIX: Final = ".ux-response.json"
REASON_MIN_CHARS: Final = 20
PURPOSE_MIN_CHARS: Final = 20
TARGETS: Final = (
    "bard",
    "circuit",
    "dashboard",
    "doc",
    "firmware",
    "fpga",
    "mech",
    "prodeng",
    "sim",
    "wire",
)
_SLUG = r"^[a-z0-9][a-z0-9._-]{0,63}$"
_SHA256 = r"^[0-9a-f]{64}$"
_TOKEN = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")

Target = Literal[
    "bard", "circuit", "dashboard", "doc", "firmware", "fpga", "mech", "prodeng", "sim", "wire"
]
Stage = Literal[
    "requirements", "design", "manufacturing_handoff", "build", "evaluation", "revision"
]
ResponseStatus = Literal["accepted", "in_progress", "done", "rejected", "deferred", "needs_info"]
GateVerdictValue = Literal["pass", "fail", "unknown"]
RequestState = Literal["new", "answered", "stale", "blocked"]
_NO_REASON_STATUSES: Final = frozenset({"accepted", "in_progress"})


def _aware(value: str) -> str:
    try:
        moment = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"not an ISO-8601 timestamp: {value!r}") from exc
    if moment.tzinfo is None:
        raise ValueError(f"timestamp needs a timezone: {value!r}")
    return value


def _non_empty(values: list[str]) -> list[str]:
    if any(not item.strip() for item in values):
        raise ValueError("entries must be non-empty strings")
    return values


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class HashedPath(_Strict):
    path: str = Field(min_length=1, description="Workspace-relative path")
    sha256: str = Field(pattern=_SHA256)


class GateVerdict(_Strict):
    gate: str = Field(min_length=1)
    verdict: GateVerdictValue


class UXRequest(_Strict):
    """A v2 request from UX-creator (strict local mirror)."""

    schema_version: Literal[2]
    system: Literal["ux-creator"]
    id: str = Field(pattern=_SLUG)
    target_agent: Target
    stage: Stage
    risk: Literal["low", "high"]
    purpose: str = Field(min_length=PURPOSE_MIN_CHARS)
    rationale: str = ""
    requested_changes: list[str] = Field(min_length=1)
    inputs: list[HashedPath] = Field(default_factory=list[HashedPath])
    expected_deliverables: list[str] = Field(min_length=1)
    acceptance: list[str] = Field(min_length=1)
    depends_on: list[str] = Field(default_factory=list[str])
    created_at: str

    _check_lists = field_validator("requested_changes", "expected_deliverables", "acceptance")(
        _non_empty
    )
    _check_time = field_validator("created_at")(_aware)

    @model_validator(mode="after")
    def _coherent(self) -> UXRequest:
        if self.risk == "high" and not _TOKEN.search(self.rationale):
            raise ValueError("high-risk requests need a rationale citing a UX job id")
        if self.id in self.depends_on:
            raise ValueError("a request cannot depend on itself")
        if any(not re.match(_SLUG, dep) for dep in self.depends_on):
            raise ValueError("depends_on entries must be request ids")
        return self


class UXResponse(_Strict):
    """A v2 response written by a sister (strict local mirror)."""

    schema_version: Literal[2] = SCHEMA_VERSION
    system: Literal["ux-creator"] = SYSTEM
    request: str = Field(pattern=_SLUG)
    responder: Target
    status: ResponseStatus
    reason: str = ""
    input_hashes: dict[str, str] = Field(default_factory=dict[str, str])
    artifacts: list[HashedPath] = Field(default_factory=list[HashedPath])
    gate_verdicts: list[GateVerdict] = Field(default_factory=list[GateVerdict])
    decision_refs: list[str] = Field(default_factory=list[str])
    impression_refs: list[str] = Field(default_factory=list[str])
    questions_for_user: list[str] = Field(default_factory=list[str])
    responded_at: str

    _check_time = field_validator("responded_at")(_aware)
    _check_questions = field_validator("questions_for_user")(_non_empty)

    @model_validator(mode="after")
    def _coherent(self) -> UXResponse:
        if self.status not in _NO_REASON_STATUSES and len(self.reason.strip()) < REASON_MIN_CHARS:
            raise ValueError(
                f"status {self.status!r} needs a reason of at least {REASON_MIN_CHARS} characters"
            )
        if any(not re.match(_SHA256, digest) for digest in self.input_hashes.values()):
            raise ValueError("input_hashes values must be sha256 digests")
        refs = self.decision_refs + self.impression_refs
        if any(not re.match(_SHA256, ref) for ref in refs):
            raise ValueError("decision_refs / impression_refs must be VRP event_ids (sha256)")
        if self.status == "done":
            bad = [g.gate for g in self.gate_verdicts if g.verdict != "pass"]
            if bad:
                raise ValueError(
                    "status 'done' with non-passing gates "
                    f"({', '.join(bad)}); answer needs_info or rejected with a reason"
                )
        return self


class RespondInput(_Strict):
    """What the agent supplies to `respond`; hashes are computed by the writer."""

    request: str = Field(pattern=_SLUG, description="Request id (the file stem)")
    status: ResponseStatus
    reason: str = ""
    artifacts: list[str] = Field(
        default_factory=list[str], description="Workspace-relative files or directories delivered"
    )
    design_reports: list[str] = Field(
        default_factory=list[str],
        description="design-report.json paths; every check becomes a gate verdict",
    )
    gate_verdicts: list[GateVerdict] = Field(default_factory=list[GateVerdict])
    decision_refs: list[str] = Field(default_factory=list[str])
    impression_refs: list[str] = Field(default_factory=list[str])
    questions_for_user: list[str] = Field(default_factory=list[str])


def liaison_dir(root: Path | None = None) -> Path:
    return (root or workspace_root()) / LIAISON_DIR


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _error_text(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or 'request'}: {err['msg']}"
            for err in exc.errors()
        )
    return str(exc)


def _load_requests(directory: Path) -> tuple[dict[str, UXRequest], list[dict[str, str]]]:
    requests: dict[str, UXRequest] = {}
    malformed: list[dict[str, str]] = []
    for path in sorted(directory.glob(f"*{REQUEST_SUFFIX}")):
        stem = path.name.removesuffix(REQUEST_SUFFIX)
        try:
            request = UXRequest.model_validate(_read_json(path))
            if request.id != stem:
                raise ValueError(f"id {request.id!r} does not match the file stem {stem!r}")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            malformed.append({"path": path.as_posix(), "detail": _error_text(exc)})
            continue
        requests[stem] = request
    return requests, malformed


def _load_responses(directory: Path) -> tuple[dict[str, UXResponse], list[dict[str, str]]]:
    responses: dict[str, UXResponse] = {}
    malformed: list[dict[str, str]] = []
    for path in sorted(directory.glob(f"*{RESPONSE_SUFFIX}")):
        stem = path.name.removesuffix(RESPONSE_SUFFIX)
        try:
            response = UXResponse.model_validate(_read_json(path))
            if response.request != stem:
                raise ValueError(f"request {response.request!r} does not match the file stem")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            malformed.append({"path": path.as_posix(), "detail": _error_text(exc)})
            continue
        responses[stem] = response
    return responses, malformed


def _current_sha(relative: str, root: Path) -> str | None:
    try:
        path = workspace_path(relative, root)
    except ValueError:
        return None
    if not path.exists():
        return None
    return sha256_file(path) if path.is_file() else tree_sha256(path)


def _ux_job_ids(root: Path) -> set[str] | None:
    """Job ids from UX contracts in the workspace (top two levels), None when there are none."""
    jobs: set[str] = set()
    found = False
    for pattern in ("*.ux.json", "*/*.ux.json", "*/*/*.ux.json"):
        for path in root.glob(pattern):
            try:
                value = _read_json(path)
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(value, dict):
                continue
            found = True
            for job in cast(list[Any], cast(dict[str, Any], value).get("jobs") or []):
                if isinstance(job, dict) and isinstance(cast(dict[str, Any], job).get("id"), str):
                    jobs.add(str(cast(dict[str, Any], job)["id"]))
    return jobs if found else None


def _stale_inputs(
    request: UXRequest, response: UXResponse | None, root: Path
) -> tuple[list[str], dict[str, str | None]]:
    current = {item.path: _current_sha(item.path, root) for item in request.inputs}
    stale: list[str] = []
    for item in request.inputs:
        now = current[item.path]
        if now is None:
            stale.append(f"{item.path}: missing")
        elif now != item.sha256:
            stale.append(f"{item.path}: changed since the request")
        elif response is not None and response.input_hashes.get(item.path) not in (None, now):
            stale.append(f"{item.path}: changed since the response")
    return stale, current


def _entry(
    stem: str,
    request: UXRequest,
    requests: Mapping[str, UXRequest],
    responses: Mapping[str, UXResponse],
    jobs: set[str] | None,
    root: Path,
) -> dict[str, Any]:
    response = responses.get(stem)
    if response is not None and response.responder != PLUGIN:
        response = None
    stale, _current = _stale_inputs(request, response, root)
    unanswered = [dep for dep in request.depends_on if dep not in responses]
    notes: list[str] = []
    if request.risk == "high":
        if jobs is None:
            notes.append("no *.ux.json in the workspace: the cited job id could not be verified")
        elif not set(_TOKEN.findall(request.rationale)) & jobs:
            notes.append("high-risk rationale cites no job id from the UX contracts")
    state: RequestState
    if stale:
        state = "stale"
    elif response is not None:
        state = "answered"
    elif unanswered:
        state = "blocked"
    else:
        state = "new"
    return {
        "id": stem,
        "state": state,
        "stage": request.stage,
        "risk": request.risk,
        "purpose": request.purpose,
        "requested_changes": list(request.requested_changes),
        "expected_deliverables": list(request.expected_deliverables),
        "acceptance": list(request.acceptance),
        "inputs": [item.model_dump() for item in request.inputs],
        "depends_on": list(request.depends_on),
        "unanswered_dependencies": unanswered,
        "missing_dependencies": [dep for dep in request.depends_on if dep not in requests],
        "stale_inputs": stale,
        "notes": notes,
        "response_status": response.status if response else None,
        "response_path": (LIAISON_DIR / f"{stem}{RESPONSE_SUFFIX}").as_posix()
        if response
        else None,
    }


def inbox(root: Path | None = None) -> dict[str, Any]:
    """Every request for wire with its state, plus malformed liaison files."""
    base = (root or workspace_root()).resolve()
    directory = liaison_dir(base)
    if not directory.is_dir():
        return {
            "verdict": "pass",
            "liaison_dir": LIAISON_DIR.as_posix(),
            "requests": [],
            "malformed": [],
            "counts": {},
            "detail": "no liaison/ directory in the workspace",
        }
    requests, bad_requests = _load_requests(directory)
    responses, bad_responses = _load_responses(directory)
    jobs = _ux_job_ids(base)
    entries = [
        _entry(stem, request, requests, responses, jobs, base)
        for stem, request in sorted(requests.items())
        if request.target_agent == PLUGIN
    ]
    malformed = [
        {**item, "path": Path(item["path"]).relative_to(base).as_posix()}
        for item in bad_requests + bad_responses
    ]
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["state"]] = counts.get(entry["state"], 0) + 1
    return {
        "verdict": "fail" if malformed else "pass",
        "liaison_dir": LIAISON_DIR.as_posix(),
        "requests": entries,
        "malformed": malformed,
        "counts": counts,
        "other_targets": len([r for r in requests.values() if r.target_agent != PLUGIN]),
    }


def _event_ids(root: Path, kinds: tuple[str, ...]) -> set[str]:
    """Event ids from intact VRP v2 logs; a broken chain refuses the answer."""
    found: set[str] = set()
    for kind in kinds:
        records, problems = _vrp.verify_log(records_dir(root) / LOG_FILES[kind], kind)
        if problems:
            raise ValueError(f"VRP {kind} log fails integrity: {problems[0]}")
        found.update(str(record.get("event_id")) for record in records)
    return found


def _report_verdicts(path: Path, label: str) -> list[GateVerdict]:
    value: Any = _read_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"{label}: design report must be a JSON object")
    checks = cast(dict[str, Any], value).get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError(f"{label}: design report lists no checks")
    worst: dict[str, GateVerdictValue] = {}
    order = {"pass": 0, "unknown": 1, "fail": 2}
    for check in cast(list[Any], checks):
        if not isinstance(check, dict):
            raise ValueError(f"{label}: malformed check")
        check = cast(dict[str, Any], check)
        gate, status = str(check.get("id")), check.get("status")
        if status not in order:
            raise ValueError(f"{label}: check {gate} has status {status!r}")
        previous = worst.get(gate, "pass")
        worst[gate] = status if order[str(status)] > order[previous] else previous
    return [GateVerdict(gate=f"{label}#{gate}", verdict=v) for gate, v in sorted(worst.items())]


def respond(payload: Mapping[str, Any], root: Path | None = None) -> dict[str, Any]:
    """Validate and write `liaison/<request>.ux-response.json`; raises ValueError on refusal."""
    base = (root or workspace_root()).resolve()
    answer = RespondInput.model_validate(dict(payload))
    directory = liaison_dir(base)
    request_path = directory / f"{answer.request}{REQUEST_SUFFIX}"
    if not request_path.is_file():
        raise ValueError(f"no request {request_path.relative_to(base).as_posix()}")
    request = UXRequest.model_validate(_read_json(request_path))
    if request.id != answer.request:
        raise ValueError("request id does not match its file stem")
    if request.target_agent != PLUGIN:
        raise ValueError(f"request targets {request.target_agent!r}, not {PLUGIN!r}")
    responses, _bad = _load_responses(directory)
    stale, current = _stale_inputs(request, None, base)
    unanswered = [dep for dep in request.depends_on if dep not in responses]
    if answer.status == "done":
        if stale:
            raise ValueError(
                "refusing 'done': request inputs changed or are missing ("
                + "; ".join(stale)
                + "); answer needs_info with a reason"
            )
        if unanswered:
            raise ValueError(f"refusing 'done': dependencies unanswered ({', '.join(unanswered)})")
    verdicts = list(answer.gate_verdicts)
    for report in answer.design_reports:
        path = workspace_path(report, base)
        verdicts.extend(_report_verdicts(path, path.relative_to(base).as_posix()))
    if answer.status == "done":
        if not verdicts:
            raise ValueError("refusing 'done' without gate verdicts (pass design_reports)")
        if not answer.artifacts:
            raise ValueError("refusing 'done' without delivered artifacts")
        if not answer.impression_refs:
            raise ValueError("refusing 'done' without a stage impression reference")
    decisions = _event_ids(base, ("decision",))
    impressions = _event_ids(base, ("stage_impression", "vision_review"))
    missing = [ref for ref in answer.decision_refs if ref not in decisions] + [
        ref for ref in answer.impression_refs if ref not in impressions
    ]
    if missing:
        raise ValueError(
            "references not found in observations/wire VRP logs: " + ", ".join(missing)
        )
    artifacts: list[dict[str, str]] = []
    for value in answer.artifacts:
        path = workspace_path(value, base)
        if not path.exists():
            raise ValueError(f"artifact does not exist: {value}")
        artifacts.append({"path": path.relative_to(base).as_posix(), "sha256": tree_sha256(path)})
    response = UXResponse(
        request=request.id,
        responder=PLUGIN,
        status=answer.status,
        reason=answer.reason,
        input_hashes={path: digest for path, digest in current.items() if digest is not None},
        artifacts=[HashedPath.model_validate(item) for item in artifacts],
        gate_verdicts=verdicts,
        decision_refs=list(answer.decision_refs),
        impression_refs=list(answer.impression_refs),
        questions_for_user=list(answer.questions_for_user),
        responded_at=datetime.now(UTC).isoformat(),
    )
    out = directory / f"{request.id}{RESPONSE_SUFFIX}"
    out.write_text(
        json.dumps(response.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    return {
        "verdict": "pass",
        "path": out.relative_to(base).as_posix(),
        "response": response.model_dump(mode="json"),
    }

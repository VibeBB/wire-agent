# pyright: reportPrivateUsage=false
"""SLP v2: strict request/response mirror, inbox states and fail-closed respond."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from test_records import IMPRESSION, _decision
from wire import liaison, records
from wire.cli import main

CREATED = "2026-10-05T09:00:00+00:00"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _request(root: Path, request_id: str, **overrides: Any) -> Path:
    body: dict[str, Any] = {
        "schema_version": 2,
        "system": "ux-creator",
        "id": request_id,
        "target_agent": "wire",
        "stage": "design",
        "risk": "low",
        "purpose": "Shorten the sensor lead so the lid closes without a loop",
        "rationale": "",
        "requested_changes": ["route RT1 at most 250 mm"],
        "inputs": [{"path": "inputs/ux.json", "sha256": _sha(root / "inputs" / "ux.json")}],
        "expected_deliverables": ["harness design report"],
        "acceptance": ["route_geometry passes"],
        "depends_on": [],
        "created_at": CREATED,
    }
    body.update(overrides)
    path = root / "liaison" / f"{request_id}.ux-request.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def _design_report(root: Path, status: str) -> str:
    report = {"checks": [{"id": "route_geometry", "subject": "RT1", "status": status}]}
    path = root / "out" / "design-report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return "out/design-report.json"


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("OPENHANDS_PROJECT_DIR", str(tmp_path))
    for name in ("liaison", "inputs", "out"):
        (tmp_path / name).mkdir()
    (tmp_path / "inputs" / "ux.json").write_text('{"jobs": []}', encoding="utf-8")
    (tmp_path / "out" / "wire-list.csv").write_text("W1,C1.1,C2.1\n", encoding="utf-8")
    return tmp_path


def _impression_ref(root: Path) -> str:
    result = records.record_impression(
        {"stage": "export", "artifacts": ["out"], "impression": IMPRESSION}, root
    )
    return str(result["record"]["event_id"])


def test_inbox_without_liaison_dir(tmp_path: Path) -> None:
    result = liaison.inbox(tmp_path)
    assert result["verdict"] == "pass"
    assert result["requests"] == []


def test_inbox_states(workspace: Path) -> None:
    _request(workspace, "lid-fit")
    _request(workspace, "after-lid", depends_on=["lid-fit"])
    _request(workspace, "for-mech", target_agent="mech")
    states = {e["id"]: e["state"] for e in liaison.inbox(workspace)["requests"]}
    assert states == {"after-lid": "blocked", "lid-fit": "new"}
    assert liaison.inbox(workspace)["other_targets"] == 1

    liaison.respond(
        {"request": "lid-fit", "status": "needs_info", "reason": "need the lid envelope first"},
        workspace,
    )
    states = {e["id"]: e["state"] for e in liaison.inbox(workspace)["requests"]}
    assert states == {"after-lid": "new", "lid-fit": "answered"}

    (workspace / "inputs" / "ux.json").write_text('{"jobs": ["x"]}', encoding="utf-8")
    entries = {e["id"]: e for e in liaison.inbox(workspace)["requests"]}
    assert entries["lid-fit"]["state"] == "stale"
    assert entries["lid-fit"]["stale_inputs"] == ["inputs/ux.json: changed since the request"]


def test_inbox_reports_malformed(workspace: Path) -> None:
    _request(workspace, "wrong-stem", id="other-id")
    _request(workspace, "short", purpose="too short")
    _request(workspace, "extra", surprise=True)
    (workspace / "liaison" / "broken.ux-request.json").write_text("{", encoding="utf-8")
    (workspace / "liaison" / "x.ux-response.json").write_text('{"status": 1}', encoding="utf-8")
    result = liaison.inbox(workspace)
    assert result["verdict"] == "fail"
    assert {Path(m["path"]).name for m in result["malformed"]} == {
        "broken.ux-request.json",
        "extra.ux-request.json",
        "short.ux-request.json",
        "wrong-stem.ux-request.json",
        "x.ux-response.json",
    }
    assert all(m["path"].startswith("liaison/") for m in result["malformed"])


def test_request_schema_rules(workspace: Path) -> None:
    base = json.loads(_request(workspace, "base").read_text(encoding="utf-8"))
    bad_overrides: tuple[dict[str, Any], ...] = (
        {"risk": "high", "rationale": ""},
        {"created_at": "2026-10-05T09:00:00"},
        {"requested_changes": []},
        {"acceptance": [" "]},
        {"depends_on": ["base"]},
        {"schema_version": 1},
        {"stage": "shipping"},
    )
    for bad in bad_overrides:
        with pytest.raises(ValidationError):
            liaison.UXRequest.model_validate({**base, **bad})
    liaison.UXRequest.model_validate({**base, "risk": "high", "rationale": "job brew_coffee"})


def test_high_risk_job_citation_is_checked(workspace: Path) -> None:
    (workspace / "kettle.ux.json").write_text('{"jobs": [{"id": "brew_coffee"}]}', "utf-8")
    _request(workspace, "cited", risk="high", rationale="serves job brew_coffee")
    _request(workspace, "uncited", risk="high", rationale="because the lid looks odd")
    notes = {e["id"]: e["notes"] for e in liaison.inbox(workspace)["requests"]}
    assert notes["cited"] == []
    assert notes["uncited"] == ["high-risk rationale cites no job id from the UX contracts"]


def test_respond_done_binds_hashes_and_refs(workspace: Path) -> None:
    _request(workspace, "lid-fit")
    impression = _impression_ref(workspace)
    decision = records.record_decision(_decision("out/wire-list.csv"), workspace)
    result = liaison.respond(
        {
            "request": "lid-fit",
            "status": "done",
            "reason": "route RT1 shortened to 240 mm and all gates pass",
            "artifacts": ["out"],
            "design_reports": [_design_report(workspace, "pass")],
            "decision_refs": [decision["record"]["event_id"]],
            "impression_refs": [impression],
        },
        workspace,
    )
    response = json.loads((workspace / result["path"]).read_text(encoding="utf-8"))
    assert liaison.UXResponse.model_validate(response).status == "done"
    assert response["input_hashes"] == {"inputs/ux.json": _sha(workspace / "inputs" / "ux.json")}
    assert response["artifacts"][0] == {
        "path": "out",
        "sha256": records.tree_sha256(workspace / "out"),
    }
    assert response["gate_verdicts"] == [
        {"gate": "out/design-report.json#route_geometry", "verdict": "pass"}
    ]


@pytest.mark.parametrize("status", ["fail", "unknown"])
def test_respond_refuses_done_on_non_passing_gate(workspace: Path, status: str) -> None:
    _request(workspace, "lid-fit")
    with pytest.raises(ValidationError, match="non-passing gates"):
        liaison.respond(
            {
                "request": "lid-fit",
                "status": "done",
                "reason": "the route was shortened but one gate is open",
                "artifacts": ["out"],
                "design_reports": [_design_report(workspace, status)],
                "impression_refs": [_impression_ref(workspace)],
            },
            workspace,
        )
    assert not (workspace / "liaison" / "lid-fit.ux-response.json").exists()
    liaison.respond(
        {
            "request": "lid-fit",
            "status": "needs_info",
            "reason": "route_geometry is not passing; need anchor positions from mech",
            "design_reports": [_design_report(workspace, status)],
        },
        workspace,
    )


def test_respond_refusals(workspace: Path) -> None:
    _request(workspace, "lid-fit")
    _request(workspace, "after-lid", depends_on=["lid-fit"])
    impression = _impression_ref(workspace)
    done: dict[str, Any] = {
        "status": "done",
        "reason": "delivered the shortened route with passing gates",
        "artifacts": ["out"],
        "design_reports": [_design_report(workspace, "pass")],
        "impression_refs": [impression],
    }
    with pytest.raises(ValueError, match="dependencies unanswered"):
        liaison.respond({**done, "request": "after-lid"}, workspace)
    with pytest.raises(ValueError, match="not found in observations/wire"):
        liaison.respond({**done, "request": "lid-fit", "impression_refs": ["0" * 64]}, workspace)
    with pytest.raises(ValueError, match="without delivered artifacts"):
        liaison.respond({**done, "request": "lid-fit", "artifacts": []}, workspace)
    with pytest.raises(ValueError, match="without a stage impression"):
        liaison.respond({**done, "request": "lid-fit", "impression_refs": []}, workspace)
    with pytest.raises(ValueError, match="without gate verdicts"):
        liaison.respond({**done, "request": "lid-fit", "design_reports": []}, workspace)
    with pytest.raises(ValueError, match="no request"):
        liaison.respond({**done, "request": "missing"}, workspace)
    with pytest.raises(ValidationError, match="reason"):
        liaison.respond({"request": "lid-fit", "status": "rejected", "reason": "no"}, workspace)
    (workspace / "inputs" / "ux.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="inputs changed"):
        liaison.respond({**done, "request": "lid-fit"}, workspace)
    _request(workspace, "for-mech", target_agent="mech")
    with pytest.raises(ValueError, match="not 'wire'"):
        liaison.respond({**done, "request": "for-mech"}, workspace)


def test_cli_ux(workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _request(workspace, "lid-fit")
    assert main(["ux", "inbox"]) == 0
    assert json.loads(capsys.readouterr().out)["requests"][0]["state"] == "new"
    answer = workspace / "answer.json"
    answer.write_text(json.dumps({"request": "lid-fit", "status": "accepted"}), encoding="utf-8")
    assert main(["ux", "respond", "--json", str(answer)]) == 0
    assert json.loads(capsys.readouterr().out)["path"] == "liaison/lid-fit.ux-response.json"
    answer.write_text(json.dumps({"request": "lid-fit", "status": "done"}), encoding="utf-8")
    assert main(["ux", "respond", "--json", str(answer)]) != 0
    assert json.loads(capsys.readouterr().out)["stage"] == "ux-respond"

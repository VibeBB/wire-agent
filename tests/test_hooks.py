"""Tests for the wire plugin hook scripts."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).parents[1] / "plugins" / "wire" / "hooks" / "scripts"
PROTECT_SCRIPT = SCRIPTS / "protect_generated.py"
REPORT_SCRIPT = SCRIPTS / "report_design_status.py"
VISION_SCRIPT = SCRIPTS / "record_vision_tool_event.py"
OBSERVE_SCRIPT = SCRIPTS / "record_image_observation.py"


def _run_hook(
    script: Path,
    payload: dict[str, Any] | str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    process_env = dict(os.environ)
    # OPENHANDS_PROJECT_DIR overrides the payload's working_dir inside the
    # record hooks; keep it from leaking the real workspace into a test.
    process_env.pop("OPENHANDS_PROJECT_DIR", None)
    if env:
        process_env.update(env)
    return subprocess.run(
        [sys.executable, str(script)],
        input=payload if isinstance(payload, str) else json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env=process_env,
    )


def test_protect_denies_file_editor_writes_to_generated_artifacts() -> None:
    for payload in (
        {
            "tool_name": "file_editor",
            "tool_input": {"command": "create", "path": "out/demo/wire-list.csv"},
        },
        {
            "tool_name": "file_editor",
            "tool_input": {"command": "str_replace", "path": "out/demo/design-report.json"},
        },
        {
            "tool_name": "file_editor",
            "tool_input": {"command": "insert", "path": "out/demo/manifest.json"},
        },
        {
            "tool_name": "file_editor",
            "tool_input": {"command": "create", "file_path": "out/demo/kbl.xml"},
        },
        {
            # Generated-name suffixes (harness-*|kbl*|vec* + .svg/.kbl/.vec)
            # are protected even without an exact artifact-name match.
            "tool_name": "file_editor",
            "tool_input": {"command": "create", "path": "out/demo/harness-alt.svg"},
        },
        {
            "tool_name": "apply_patch",
            "tool_input": {"patch": "+++ b/out/demo/cut-table.csv"},
        },
    ):
        result = _run_hook(PROTECT_SCRIPT, payload)
        assert result.returncode == 2, payload
        assert "generated artifacts" in result.stderr


def test_protect_allows_views_and_non_artifact_writes() -> None:
    for payload in (
        {
            "tool_name": "file_editor",
            "tool_input": {"command": "view", "path": "out/demo/wire-list.csv"},
        },
        {
            "tool_name": "file_editor",
            "tool_input": {"command": "create", "path": "docs/notes.md"},
        },
        {
            # Artifact names inside file bodies are ignored — only paths gate.
            "tool_name": "file_editor",
            "tool_input": {
                "command": "create",
                "path": "docs/notes.md",
                "file_text": "see wire-list.csv and design-report.json",
            },
        },
        {
            # A .svg that is not a generated artifact name is writable.
            "tool_name": "file_editor",
            "tool_input": {"command": "create", "path": "out/demo/logo.svg"},
        },
        {
            "tool_name": "apply_patch",
            "tool_input": {"patch": "+++ b/docs/notes.md"},
        },
        {
            "tool_name": "browser",
            "tool_input": {"url": "file:///out/demo/wire-list.csv"},
        },
    ):
        assert _run_hook(PROTECT_SCRIPT, payload).returncode == 0, payload


def test_protect_denies_terminal_writes_to_generated_artifacts() -> None:
    for command in (
        "echo x > out/wire-list.csv",
        "echo x >> bom.json",
        "cat a | tee cut-table.csv",
        "cp src.csv wire-list.csv",
        "mv draft.json design-report.json",
        "dd if=x of=vec.xml",
        "sed -i s/a/b/ manifest.json",
        "install -m644 src provenance.json",
        "touch harness-diagram.png",
        "rm out/design-report.md",
        "python3 gen.py && cp x wire-list.csv",
        "cmd 2> design-report.md",
    ):
        payload = {"tool_name": "terminal", "tool_input": {"command": command}}
        assert _run_hook(PROTECT_SCRIPT, payload).returncode == 2, command


def test_protect_allows_terminal_reads_and_content_mentions() -> None:
    for command in (
        "cat out/wire-list.csv",
        "find . -name 'design-report.json'",
        "grep -r bom.json out/",
        "cp out/wire-list.csv backups/wire-list.csv.bak",
        "tar czf artifacts.tgz out/wire-list.csv",
        "echo 'see wire-list.csv' > notes.md",
        "cmd >&2",
        "cmd 2>&1 | grep design-report",
    ):
        payload = {"tool_name": "terminal", "tool_input": {"command": command}}
        assert _run_hook(PROTECT_SCRIPT, payload).returncode == 0, command


def test_protect_rejects_malformed_input() -> None:
    result = _run_hook(PROTECT_SCRIPT, "{not-json")
    assert result.returncode == 2
    assert "invalid hook input" in result.stderr


def _write_report(path: Path, verdict: str, checks: list[dict[str, Any]] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "gate": "wire-harness",
                "design": {"name": "fixture"},
                "verdict": verdict,
                "summary": {},
                "checks": checks or [],
            }
        ),
        encoding="utf-8",
    )


def test_report_design_status_pass_and_fail(tmp_path: Path) -> None:
    _write_report(tmp_path / "out" / "ok" / "design-report.json", "pass")
    _write_report(
        tmp_path / "out" / "bad" / "design-report.json",
        "fail",
        [
            {"id": "bend-radius", "subject": "leg-1", "status": "fail"},
            {"id": "ampacity", "subject": "w2", "status": "unknown"},
            {"id": "fill", "subject": "c1", "status": "pass"},
        ],
    )

    result = _run_hook(REPORT_SCRIPT, {"working_dir": str(tmp_path)})

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["decision"] == "allow"
    context = output["additionalContext"]
    assert "verdict=pass" in context
    assert "verdict=fail" in context
    assert "state each failing gate explicitly" in context
    assert "bend-radius:leg-1" in context
    assert "ampacity:w2" in context
    assert "fill:c1" not in context


def test_report_design_status_none(tmp_path: Path) -> None:
    result = _run_hook(REPORT_SCRIPT, {"working_dir": str(tmp_path)})

    assert result.returncode == 0
    assert "No design reports found" in json.loads(result.stdout)["additionalContext"]


def test_report_design_status_ignores_skipped_and_too_deep_paths(tmp_path: Path) -> None:
    _write_report(tmp_path / ".venv" / "pkg" / "design-report.json", "fail")
    _write_report(tmp_path / "a" / "b" / "c" / "d" / "e" / "design-report.json", "fail")

    result = _run_hook(REPORT_SCRIPT, {"working_dir": str(tmp_path)})

    assert result.returncode == 0
    assert "No design reports found" in json.loads(result.stdout)["additionalContext"]


def test_report_design_status_malformed(tmp_path: Path) -> None:
    report = tmp_path / "design-report.json"
    report.write_text("{not-json", encoding="utf-8")

    result = _run_hook(REPORT_SCRIPT, {"working_dir": str(tmp_path)})

    assert result.returncode == 1
    assert "report_design_status:" in result.stderr


def test_report_design_status_missing_verdict(tmp_path: Path) -> None:
    report = tmp_path / "design-report.json"
    report.write_text(json.dumps({"checks": []}), encoding="utf-8")

    result = _run_hook(REPORT_SCRIPT, {"working_dir": str(tmp_path)})

    assert result.returncode == 1
    assert "report_design_status:" in result.stderr


def _vision_payload(tmp_path: Path, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "working_dir": str(tmp_path),
        "session_id": "session-1",
        "tool_name": "inspect_image_with_vision",
        "tool_input": {"image_index": 0, "question": "Check the splice table"},
        "tool_response": {
            "answer": "All splices look correct.",
            "profile_name": "vision",
            "model": "vision-model-1",
        },
    }
    payload.update(overrides)
    return payload


def _vision_events(tmp_path: Path) -> list[dict[str, Any]]:
    path = tmp_path / ".openhands" / "wire" / "vision-tool-events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_record_vision_tool_event_appends_records(tmp_path: Path) -> None:
    payload = _vision_payload(tmp_path)

    assert _run_hook(VISION_SCRIPT, payload).returncode == 0

    records = _vision_events(tmp_path)
    assert len(records) == 1
    record = records[0]
    assert record["tool_name"] == "inspect_image_with_vision"
    assert record["image_index"] == 0
    assert record["question"] == "Check the splice table"
    assert record["profile_name"] == "vision"
    assert record["model"] == "vision-model-1"
    assert record["response_sha256"].startswith("sha256:")
    assert record["session_id"] == "session-1"
    assert record["sequence"] == 1
    assert record["event_id"]

    assert _run_hook(VISION_SCRIPT, payload).returncode == 0

    records = _vision_events(tmp_path)
    assert [r["sequence"] for r in records] == [1, 2]
    assert records[0]["event_id"] != records[1]["event_id"]


def test_record_vision_tool_event_honors_events_override(tmp_path: Path) -> None:
    override = tmp_path / "custom" / "events.jsonl"

    result = _run_hook(
        VISION_SCRIPT,
        _vision_payload(tmp_path),
        env={"WIRE_VISION_TOOL_EVENTS": str(override)},
    )

    assert result.returncode == 0
    assert len(override.read_text(encoding="utf-8").splitlines()) == 1
    assert not (tmp_path / ".openhands").exists()


def test_record_vision_tool_event_skips_non_records(tmp_path: Path) -> None:
    for response in (
        {"error": "vision profile missing"},
        {"is_error": True, "answer": "x", "profile_name": "vision", "model": "m"},
        {"answer": "   ", "profile_name": "vision", "model": "m"},
        {"answer": "ok", "profile_name": "", "model": "m"},
        {"answer": "ok", "profile_name": "vision"},
        {"answer": "ok"},
        "not-a-dict",
    ):
        payload = _vision_payload(tmp_path, tool_response=response)
        assert _run_hook(VISION_SCRIPT, payload).returncode == 0, response
    payload = _vision_payload(tmp_path, tool_name="wire_export")
    assert _run_hook(VISION_SCRIPT, payload).returncode == 0
    assert _run_hook(VISION_SCRIPT, "{not-json").returncode == 0
    assert _vision_events(tmp_path) == []


_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c626001000000ffff03000006000557bfabd40000000049"
    "454e44ae426082"
)


def _observations(tmp_path: Path) -> list[dict[str, Any]]:
    path = tmp_path / ".openhands" / "wire" / "image-observations.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_record_image_observation_logs_file_editor_view(tmp_path: Path) -> None:
    image = tmp_path / "out" / "demo" / "harness-diagram.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(_PNG)
    payload = {
        "working_dir": str(tmp_path),
        "tool_name": "file_editor",
        # A relative path resolves against working_dir.
        "tool_input": {"command": "view", "path": "out/demo/harness-diagram.png"},
        "tool_response": {"output": "ok"},
        "session_id": "s1",
    }

    assert _run_hook(OBSERVE_SCRIPT, payload).returncode == 0

    records = _observations(tmp_path)
    assert len(records) == 1
    assert records[0]["tool_name"] == "file_editor"
    assert records[0]["image_path"] == str(image)
    assert records[0]["image_sha256"] == hashlib.sha256(_PNG).hexdigest()
    assert records[0]["session_id"] == "s1"
    assert records[0]["sequence"] == 1
    assert records[0]["event_id"]


def test_record_image_observation_logs_export_response_paths(tmp_path: Path) -> None:
    image = tmp_path / "diagram.png"
    image.write_bytes(_PNG)
    payload = {
        "working_dir": str(tmp_path),
        "tool_name": "wire_export",
        "tool_input": {},
        # The same path mentioned twice is recorded once.
        "tool_response": {
            "content": [{"type": "text", "text": f"wrote {image}; reopened {image}"}]
        },
    }

    assert _run_hook(OBSERVE_SCRIPT, payload).returncode == 0

    records = _observations(tmp_path)
    assert [r["image_path"] for r in records] == [str(image)]


def test_record_image_observation_honors_observations_override(tmp_path: Path) -> None:
    image = tmp_path / "diagram.png"
    image.write_bytes(_PNG)
    override = tmp_path / "custom" / "observations.jsonl"
    payload = {
        "working_dir": str(tmp_path),
        "tool_name": "file_editor",
        "tool_input": {"command": "view", "path": str(image)},
        "tool_response": {"output": "ok"},
    }

    result = _run_hook(OBSERVE_SCRIPT, payload, env={"WIRE_IMAGE_OBSERVATIONS": str(override)})

    assert result.returncode == 0
    assert len(override.read_text(encoding="utf-8").splitlines()) == 1
    assert not (tmp_path / ".openhands").exists()


def test_record_image_observation_skips_non_observations(tmp_path: Path) -> None:
    image = tmp_path / "diagram.png"
    image.write_bytes(_PNG)
    for payload in (
        {
            # create is a write, not an observation
            "working_dir": str(tmp_path),
            "tool_name": "file_editor",
            "tool_input": {"command": "create", "path": str(image)},
            "tool_response": {"output": "ok"},
        },
        {
            # .svg is not an observed image suffix
            "working_dir": str(tmp_path),
            "tool_name": "file_editor",
            "tool_input": {"command": "view", "path": "diagram.svg"},
            "tool_response": {"output": "ok"},
        },
        {
            # error responses are not recorded
            "working_dir": str(tmp_path),
            "tool_name": "wire_export",
            "tool_input": {},
            "tool_response": {"error": "export failed"},
        },
        {
            # unobserved tool
            "working_dir": str(tmp_path),
            "tool_name": "terminal",
            "tool_input": {"command": "cat diagram.png"},
            "tool_response": {"output": "ok"},
        },
        {
            # a mentioned path that does not exist is not recorded
            "working_dir": str(tmp_path),
            "tool_name": "wire_export",
            "tool_input": {},
            "tool_response": {"content": [{"type": "text", "text": "wrote /no/such.png"}]},
        },
    ):
        assert _run_hook(OBSERVE_SCRIPT, payload).returncode == 0, payload
    assert _run_hook(OBSERVE_SCRIPT, "{not-json").returncode == 0
    assert _observations(tmp_path) == []


ATTACH_SCRIPT = (
    Path(__file__).parents[1] / "plugins" / "wire" / "hooks" / "scripts" / "intake_attachments.py"
)


def _write_event(events: Path, name: str, source: str, urls: list[str]) -> None:
    event = {
        "id": name,
        "source": source,
        "llm_message": {
            "role": "user",
            "content": (
                [{"type": "image", "image_urls": urls}]
                if urls
                else [{"type": "text", "text": "hi"}]
            ),
        },
    }
    (events / name).write_text(json.dumps(event), encoding="utf-8")


def _run_attach_hook(
    payload: dict[str, Any], events_dir: Path | None
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    if events_dir is not None:
        env["WIRE_AGENT_EVENTS_DIR"] = str(events_dir)
    else:
        env.pop("WIRE_AGENT_EVENTS_DIR", None)
    return subprocess.run(
        [sys.executable, str(ATTACH_SCRIPT)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def test_intake_attachments_materializes_user_images(tmp_path: Path) -> None:
    events = tmp_path / "events"
    events.mkdir()
    encoded = "data:image/png;base64," + base64.b64encode(_PNG).decode()
    _write_event(events, "event-1.json", "user", [encoded])
    _write_event(events, "event-2.json", "agent", [encoded])
    _write_event(events, "event-3.json", "user", [])
    workdir = tmp_path / "work"
    workdir.mkdir()

    payload = {"working_dir": str(workdir)}
    result = _run_attach_hook(payload, events)

    assert result.returncode == 0
    attachments = workdir / "intake" / "attachments"
    images = list(attachments.glob("*.png"))
    assert len(images) == 1
    assert images[0].read_bytes() == _PNG
    records = [
        json.loads(line)
        for line in (attachments / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 1
    assert records[0]["sha256"] == hashlib.sha256(_PNG).hexdigest()
    assert records[0]["materialized"] is True
    # second run is a no-op
    assert _run_attach_hook(payload, events).returncode == 0
    assert len(list(attachments.glob("*.png"))) == 1
    assert len((attachments / "manifest.jsonl").read_text(encoding="utf-8").splitlines()) == 1


def test_intake_attachments_records_non_data_urls(tmp_path: Path) -> None:
    events = tmp_path / "events"
    events.mkdir()
    _write_event(events, "event-1.json", "user", ["https://example.com/board.png"])
    workdir = tmp_path / "work"
    workdir.mkdir()

    result = _run_attach_hook({"working_dir": str(workdir)}, events)

    assert result.returncode == 0
    manifest = workdir / "intake" / "attachments" / "manifest.jsonl"
    record = json.loads(manifest.read_text(encoding="utf-8").splitlines()[0])
    assert record["materialized"] is False
    assert record["reason"] == "non-data-url"


def test_intake_attachments_fails_open_without_events_dir(tmp_path: Path) -> None:
    result = _run_attach_hook({"working_dir": str(tmp_path)}, None)
    assert result.returncode == 0
    assert not (tmp_path / "intake").exists()


def test_intake_attachments_uses_session_default_path(tmp_path: Path) -> None:
    home = tmp_path / "home"
    events = home / ".openhands" / "agent-canvas" / "dev_conversations" / "session-9" / "events"
    events.mkdir(parents=True)
    encoded = "data:image/png;base64," + base64.b64encode(_PNG).decode()
    _write_event(events, "event-1.json", "user", [encoded])
    workdir = tmp_path / "work"
    workdir.mkdir()

    env = dict(os.environ)
    env.pop("WIRE_AGENT_EVENTS_DIR", None)
    env["HOME"] = str(home)
    result = subprocess.run(
        [sys.executable, str(ATTACH_SCRIPT)],
        input=json.dumps({"working_dir": str(workdir), "session_id": "session-9"}),
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )

    assert result.returncode == 0
    assert list((workdir / "intake" / "attachments").glob("*.png"))

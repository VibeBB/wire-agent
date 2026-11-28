"""Structural guards for the CI invariants the workflow audit found.

The defects it caught — a dead smoke-upload step whose hashFiles() could
never see $RUNNER_TEMP, an imagetools invocation without --tag, a
promote-by-tag that ran before the SARIF gate, and a pin-PR dispatch that
duplicated pull_request runs — are all mechanically checkable, so they get
regression tests here instead of another audit.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
WATCHER = "main-ci-failure-issue.yml"
POST_MERGE_WORKFLOWS = {"ci.yml", "locked-image-check.yml", "workflow-lint.yml"}
# Byte-identical across the family (check_shared_workflows.py); local
# invariants cannot tighten them.
SHARED_CANON = {
    "pr-branch-cleanup.yml",
    "dependency-review.yml",
    "scorecard.yml",
    "workflow-lint.yml",
    "main-ci-failure-issue.yml",
}


def _load(name: str) -> dict[Any, Any]:
    # YAML keys are not necessarily strings: PyYAML parses the bare `on:`
    # key as boolean True (YAML 1.1).
    data: dict[Any, Any] = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    return data


def _flatten_steps(steps: list[Any]) -> list[dict[Any, Any]]:
    # A `parallel:` entry's members all complete before the steps that
    # follow the group, so splicing them into the sequence keeps ordering
    # assertions (gate-before-promote) and per-step checks (if:, uses:)
    # meaningful for nested steps.
    flat: list[dict[Any, Any]] = []
    for step in steps:
        members = cast(dict[Any, Any], step).get("parallel")
        if members:
            flat.extend(cast(list[dict[Any, Any]], members))
        else:
            flat.append(cast(dict[Any, Any], step))
    return flat


def _on(data: dict[Any, Any]) -> dict[Any, Any]:
    on: dict[Any, Any] = data.get("on") or data.get(True) or {}
    return on


def _workflow_files() -> list[Path]:
    return sorted(WORKFLOWS.glob("*.yml"))


def test_every_workflow_declares_permissions_concurrency_and_timeouts() -> None:
    for path in _workflow_files():
        data = _load(path.name)
        assert "permissions" in data, f"{path.name}: missing top-level permissions"
        assert "concurrency" in data, f"{path.name}: missing concurrency block"
        jobs: dict[Any, Any] = data.get("jobs") or {}
        for job_name, job in jobs.items():
            if "uses" in job:  # reusable-workflow call, no runner of its own
                continue
            assert "timeout-minutes" in job, f"{path.name}:{job_name} missing timeout-minutes"


def test_every_uses_is_a_40_char_sha_pin_with_version_comment() -> None:
    pin = re.compile(r"uses:\s*[\w.-]+/[\w.-]+(?:/[\w.-]+)*@([0-9a-f]{40})\s+#\s*v[\w.-]+")
    for path in _workflow_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "uses:" not in line:
                continue
            if pin.search(line):
                continue
            stripped = line.split("#", 1)[0]
            assert not re.search(r"uses:\s*\S+@\S+", stripped), (
                f"{path.name}:{lineno} uses: pin must be a 40-char SHA with a '# v*' comment"
            )


def _runs_on_main(on: dict[Any, Any]) -> bool:
    if "schedule" in on or "workflow_dispatch" in on:
        return True
    push: dict[Any, Any] = on.get("push") or {}
    return "main" in (push.get("branches") or [])


def test_failure_watchlist_covers_every_main_workflow() -> None:
    watcher = _load(WATCHER)
    watched: set[str] = set(_on(watcher)["workflow_run"]["workflows"])
    expected: set[str] = set()
    for path in _workflow_files():
        if path.name == WATCHER:
            continue
        data = _load(path.name)
        if _runs_on_main(_on(data)):
            expected.add(data["name"])
    assert watched == expected, (
        f"{WATCHER} watchlist drift: missing {sorted(expected - watched)}, "
        f"extra {sorted(watched - expected)}"
    )


def test_container_audit_cis_aggregation_walks_nested_results_and_fails_loud() -> None:
    text = (WORKFLOWS / "container-audit.yml").read_text(encoding="utf-8")
    script = (ROOT / "scripts/container_hardening_report.py").read_text(encoding="utf-8")
    # The CIS scan exits 0 even on an empty payload, so the workflow must
    # gate the report on a non-empty payload check, with one retry.
    assert "--check-cis trivy-cis.json" in text
    assert "empty payload; retrying once" in text
    assert "python3 scripts/container_hardening_report.py" in text
    # trivy --compliance nests MisconfSummary under Results[].Results[]; a
    # flat read silently reports 0/0, so the aggregator must recurse and
    # must fail when the scan produced nothing.
    assert "def _summaries(node" in script
    assert "yield from _summaries(child)" in script
    assert 'sys.exit("Docker CIS scan produced no results")' in script


def test_container_audit_resolves_the_lock_by_explicit_key() -> None:
    text = (WORKFLOWS / "container-audit.yml").read_text(encoding="utf-8")
    # sorted(d)[0] silently tracks whatever key sorts first.
    assert "sorted(d)[0]" not in text
    assert 'data.get("wire_tools")' in text
    assert 'sys.exit("wire_tools image does not match ghcr.io/vibebb/wire-tools")' in text


def test_candidate_workflow_never_promotes_latest() -> None:
    data = _load("publish-wire-images.yml")
    steps = _flatten_steps(data["jobs"]["publish"]["steps"])
    for step in steps:
        if "docker/build-push-action" in (step.get("uses") or ""):
            with_block: dict[Any, Any] = step.get("with") or {}
            tags: str = with_block.get("tags") or ""
            assert ":latest" not in tags, "build-push must push immutable tags only"
    assert all("imagetools create" not in (step.get("run") or "") for step in steps)
    gate = next(i for i, s in enumerate(steps) if s.get("name") == "Scan tools image (Trivy SARIF)")
    lock = next(
        i for i, s in enumerate(steps) if s.get("name") == "Update digest lock and merge PR"
    )
    assert gate < lock, "only a gated candidate may be pinned"


def test_release_promotion_is_tag_only_and_production_gated() -> None:
    data = _load("release.yml")
    triggers = _on(data)
    assert triggers["push"] == {"tags": ["v*"]}
    assert "workflow_dispatch" not in triggers
    jobs = data["jobs"]
    assert jobs["validate"]["if"] == "github.event_name == 'push'"
    publish = jobs["publish"]
    assert publish["environment"] == "production"
    assert set(publish["needs"]) == {"validate", "build"}
    steps = _flatten_steps(publish["steps"])
    commands = [step.get("run") or "" for step in steps]
    guard = next(i for i, run in enumerate(commands) if "--publish-check" in run)
    promote = next(i for i, run in enumerate(commands) if "imagetools create" in run)
    release = next(i for i, run in enumerate(commands) if "gh release create" in run)
    assert guard < promote < release
    assert '--tag "$package:$GITHUB_REF_NAME" --tag "$package:latest"' in commands[promote]
    assert "--verify-tag" in commands[release]
    assert "--draft" not in commands[release]


def test_publish_dispatch_is_limited_to_main_or_pr() -> None:
    data = _load("publish-wire-images.yml")
    job: dict[Any, Any] = data["jobs"]["publish"]
    assert job.get("if") == (
        "github.ref == 'refs/heads/main' || github.event_name == 'pull_request'"
    )


def _job_steps(data: dict[Any, Any]) -> list[tuple[str, dict[Any, Any]]]:
    steps: list[tuple[str, dict[Any, Any]]] = []
    jobs = cast(dict[Any, Any], data.get("jobs") or {})
    for job_name, job in jobs.items():
        job_steps = cast(list[Any], cast(dict[Any, Any], job).get("steps") or [])
        for step in _flatten_steps(job_steps):
            steps.append((str(job_name), step))
    return steps


def test_no_hashfiles_condition_references_paths_outside_the_workspace() -> None:
    # hashFiles() only evaluates under GITHUB_WORKSPACE: a glob built on
    # runner.temp or format('{0}/...', runner.temp) is always empty and
    # silently skips the step (the dead smoke-upload regression).
    for path in _workflow_files():
        data = _load(path.name)
        for job_name, step in _job_steps(data):
            condition = str(step.get("if") or "")
            if "hashFiles" not in condition:
                continue
            assert "runner.temp" not in condition and "format(" not in condition, (
                f"{path.name}:{job_name}:{step.get('name')}: hashFiles() "
                "cannot see paths outside GITHUB_WORKSPACE"
            )


def test_every_upload_sarif_step_is_gated_by_hashfiles() -> None:
    for path in _workflow_files():
        if path.name in SHARED_CANON:
            continue
        data = _load(path.name)
        for job_name, step in _job_steps(data):
            if "codeql-action/upload-sarif" not in (step.get("uses") or ""):
                continue
            condition = str(step.get("if") or "")
            assert "hashFiles" in condition, (
                f"{path.name}:{job_name}:{step.get('name')}: "
                "upload-sarif without a hashFiles guard fails the run "
                "when the scan produced no SARIF"
            )


def test_pin_pr_post_merge_workflow_list_matches_the_publisher() -> None:
    publish = (WORKFLOWS / "publish-wire-images.yml").read_text(encoding="utf-8")
    sweep = (WORKFLOWS / "digest-lock-sweep.yml").read_text(encoding="utf-8")
    helper = (ROOT / "scripts/publish_image_pin_pr.sh").read_text(encoding="utf-8")
    sweep_script = (ROOT / "scripts/digest_lock_sweep.sh").read_text(encoding="utf-8")
    for workflow in POST_MERGE_WORKFLOWS:
        assert workflow in publish, f"publish does not dispatch {workflow} post-merge"
        assert workflow in sweep, f"sweep does not dispatch {workflow} post-merge"
    assert "ci.yml workflow-lint.yml" in helper, (
        "the pin-PR dispatch set must cover ci.yml and workflow-lint.yml"
    )
    assert "SWEEP_POST_MERGE_WORKFLOWS" in sweep_script


def test_locked_image_check_gates_pull_requests_on_the_lock_paths() -> None:
    data = _load("locked-image-check.yml")
    pull_request: dict[Any, Any] = _on(data).get("pull_request") or {}
    paths = set(pull_request.get("paths") or [])
    assert "docker/image-digests.json" in paths
    assert "plugins/wire/skills/wire-workflow/tools-image.json" in paths

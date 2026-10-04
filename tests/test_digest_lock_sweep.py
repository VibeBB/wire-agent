from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPOSITORY = f"VibeBB/{Path(__file__).parents[1].name}"

# The stub's behavior is selected by GH_STUB_CASE:
#   clean / blocked / behind / dirty — mergeable_state for open PR #1
#   merge-fails — merge attempt fails, auto-merge arm succeeds
#   merged-pr — no open PRs, one digest-lock PR merged just now, no dispatch
#   merged-pr-covered — same but ci.yml was already dispatched since
#   dispatch-fails — ci.yml dispatch fails after a successful merge
STUB = """#!/usr/bin/env bash
set -eu
printf '%s\\n' "$*" >> "$GH_STUB_CALLS"
if [[ "$1 $2" == "pr list" ]]; then
  if [[ "$*" == *"--state merged"* ]]; then
    case "$GH_STUB_CASE" in
      merged-pr|merged-pr-covered) date -u +%Y-%m-%dT%H:%M:%SZ ;;
    esac
  else
    case "$GH_STUB_CASE" in
      no-prs|merged-pr|merged-pr-covered) : ;;
      *) printf '1\\n' ;;
    esac
  fi
elif [[ "$1" == "api" ]]; then
  case "$GH_STUB_CASE" in
    clean|merge-fails|dispatch-fails) printf 'clean\\n' ;;
    blocked) printf 'blocked\\n' ;;
    behind) printf 'behind\\n' ;;
    dirty) printf 'dirty\\n' ;;
    *) printf 'unknown\\n' ;;
  esac
elif [[ "$1 $2" == "pr merge" ]]; then
  if [[ "$GH_STUB_CASE" == "merge-fails" && "$*" != *"--auto"* ]]; then
    exit 1
  fi
elif [[ "$1 $2" == "run list" ]]; then
  # The real call passes --jq 'length', so emit the post-jq scalar.
  case "$GH_STUB_CASE" in
    merged-pr-covered) printf '1\\n' ;;
    *) printf '0\\n' ;;
  esac
elif [[ "$1 $2" == "workflow run" ]]; then
  if [[ "$GH_STUB_CASE" == "dispatch-fails" && "$*" == *ci.yml* ]]; then
    printf 'graphQL error\\n' >&2
    exit 1
  fi
fi
"""


@pytest.fixture
def sweep(tmp_path: Path) -> tuple[Path, dict[str, str], Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(STUB, encoding="utf-8")
    gh.chmod(0o755)
    calls = tmp_path / "calls.log"
    summary = tmp_path / "summary.md"
    env = os.environ.copy()
    # A BASH_ENV-exported gh() shell function would shadow the PATH stub
    # inside the script under test (verify_all runs with one set).
    env.pop("BASH_ENV", None)
    env = {key: value for key, value in env.items() if not key.startswith("BASH_FUNC_gh")}
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "GITHUB_REPOSITORY": REPOSITORY,
            "GITHUB_STEP_SUMMARY": str(summary),
            "GH_STUB_CALLS": str(calls),
            "SWEEP_POST_MERGE_WORKFLOWS": "ci.yml locked-image-check.yml workflow-lint.yml",
        }
    )
    return Path(__file__).parents[1] / "scripts/digest_lock_sweep.sh", env, calls


def run_sweep(
    sweep: tuple[Path, dict[str, str], Path],
    case: str,
) -> tuple[subprocess.CompletedProcess[str], str, str]:
    script, env, calls = sweep
    env["GH_STUB_CASE"] = case
    result = subprocess.run(
        ["bash", str(script)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    summary_path = Path(env["GITHUB_STEP_SUMMARY"])
    summary = summary_path.read_text(encoding="utf-8") if summary_path.exists() else ""
    log = calls.read_text(encoding="utf-8") if calls.exists() else ""
    return result, summary, log


def test_no_open_prs_no_dispatch(
    sweep: tuple[Path, dict[str, str], Path],
) -> None:
    result, summary, log = run_sweep(sweep, "no-prs")

    assert result.returncode == 0
    assert "no open digest-lock PRs" in summary
    assert "workflow run" not in log


@pytest.mark.parametrize("state", ["clean", "blocked", "behind"])
def test_mergeable_states_merge_and_dispatch(
    sweep: tuple[Path, dict[str, str], Path], state: str
) -> None:
    result, summary, log = run_sweep(sweep, state)

    assert result.returncode == 0
    assert f"merged https://github.com/{REPOSITORY}/pull/1 (was {state})" in summary
    assert "pr merge" in log and "--auto" not in log
    assert f"workflow run ci.yml --repo {REPOSITORY} --ref main" in log
    assert f"workflow run locked-image-check.yml --repo {REPOSITORY} --ref main" in log
    assert f"workflow run workflow-lint.yml --repo {REPOSITORY} --ref main" in log
    assert "dispatched ci.yml" in summary


def test_dirty_pr_is_skipped(
    sweep: tuple[Path, dict[str, str], Path],
) -> None:
    result, summary, log = run_sweep(sweep, "dirty")

    assert result.returncode == 0
    assert "skipped (mergeable_state=dirty)" in summary
    assert "pr merge" not in log
    assert "workflow run" not in log


def test_failed_merge_arms_auto_merge(
    sweep: tuple[Path, dict[str, str], Path],
) -> None:
    result, summary, log = run_sweep(sweep, "merge-fails")

    assert result.returncode == 0
    assert "left open (clean; auto-merge armed)" in summary
    assert "--auto --squash --delete-branch" in log
    # The armed auto-merge will complete later; the backstop covers it.
    assert "workflow run" not in log


def test_recent_merge_without_dispatch_triggers_backstop(
    sweep: tuple[Path, dict[str, str], Path],
) -> None:
    result, _summary, log = run_sweep(sweep, "merged-pr")

    assert result.returncode == 0
    assert "--state merged" in log
    assert f"workflow run ci.yml --repo {REPOSITORY} --ref main" in log


def test_recent_merge_with_dispatch_is_not_repeated(
    sweep: tuple[Path, dict[str, str], Path],
) -> None:
    result, _summary, log = run_sweep(sweep, "merged-pr-covered")

    assert result.returncode == 0
    assert "--state merged" in log
    assert "workflow run" not in log


def test_dispatch_failure_fails_the_job(
    sweep: tuple[Path, dict[str, str], Path],
) -> None:
    result, summary, log = run_sweep(sweep, "dispatch-fails")

    assert result.returncode == 1
    assert "::error::failed to dispatch ci.yml on main" in summary
    # The remaining workflows are still dispatched after the failure.
    assert "workflow run locked-image-check.yml" in log
    assert "workflow run workflow-lint.yml" in log


def test_sweep_workflow_calls_the_script() -> None:
    workflow = (Path(__file__).parents[1] / ".github/workflows/digest-lock-sweep.yml").read_text(
        encoding="utf-8"
    )

    assert "run: bash scripts/digest_lock_sweep.sh" in workflow
    assert "actions/checkout" in workflow
    assert "egress-policy: block" in workflow
    assert (
        'SWEEP_POST_MERGE_WORKFLOWS: "ci.yml locked-image-check.yml workflow-lint.yml"' in workflow
    )

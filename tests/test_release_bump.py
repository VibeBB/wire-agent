from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = f"VibeBB/{REPO_ROOT.name}"
SCRIPT = REPO_ROOT / "scripts/release_bump.sh"
PR_URL = f"https://github.com/{REPOSITORY}/pull/77"

SKILLS = (
    "wire-connectivity",
    "wire-contract",
    "wire-gates",
    "wire-workflow",
)

GH_STUB = """#!/usr/bin/env bash
set -eu
printf '%s\\n' "$*" >> "$GH_STUB_CALLS"
case "$1 $2" in
  "pr list") printf '%s\\n' "${GH_STUB_EXISTING:-}" ;;
  "pr create") printf '%s\\n' "$GH_STUB_PR_URL" ;;
  *) printf 'Unexpected command: %s\\n' "$*" >&2; exit 1 ;;
esac
"""


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return proc.stdout.strip()


def _write_version_files(work: Path, version: str) -> None:
    for rel in (
        "plugins/wire/.plugin",
        "scripts",
        *(f"plugins/wire/skills/{skill}" for skill in SKILLS),
    ):
        (work / rel).mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO_ROOT / "scripts/bump_version.py", work / "scripts/bump_version.py")
    (work / "plugins/wire/.plugin/plugin.json").write_text(
        f'{{\n  "version": "{version}"\n}}\n', encoding="utf-8"
    )
    (work / "pyproject.toml").write_text(
        f'[project]\nname = "wire-agent"\nversion = "{version}"\n',
        encoding="utf-8",
    )
    for skill in SKILLS:
        (work / f"plugins/wire/skills/{skill}/SKILL.md").write_text(
            f"---\nversion: {version}\n---\n", encoding="utf-8"
        )
    (work / "uv.lock").write_text(
        f'[[package]]\nname = "wire-agent"\nversion = "{version}"\n',
        encoding="utf-8",
    )


def make_release_repo(tmp_path: Path) -> tuple[Path, Path, dict[str, str], Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(GH_STUB, encoding="utf-8")
    gh.chmod(0o755)

    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-b", "main")
    _git(work, "config", "user.name", "Test")
    _git(work, "config", "user.email", "test@example.com")
    _write_version_files(work, "1.2.3")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "initial")

    bare = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", str(bare)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    _git(work, "remote", "add", "origin", str(bare))
    _git(work, "push", "-u", "origin", "main")

    calls = tmp_path / "calls.log"
    env = os.environ.copy()
    # A BASH_ENV-exported gh() shell function would shadow the PATH stub
    # inside the script under test (verify_all runs with one set).
    env.pop("BASH_ENV", None)
    env = {key: value for key, value in env.items() if not key.startswith("BASH_FUNC_gh")}
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "BUMP": "patch",
            "SET_VERSION": "",
            "DRY_RUN": "false",
            "GH_TOKEN": "stub",
            "GITHUB_REPOSITORY": REPOSITORY,
            "RELEASE_BUMP_REPO_ROOT": str(work),
            "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md"),
            "GITHUB_RUN_ID": "4242",
            "GITHUB_SERVER_URL": "https://github.com",
            "GH_STUB_CALLS": str(calls),
            "GH_STUB_PR_URL": PR_URL,
        }
    )
    return work, bare, env, calls


@pytest.fixture
def release_repo(tmp_path: Path) -> tuple[Path, Path, dict[str, str], Path]:
    return make_release_repo(tmp_path)


def run_bump(work: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=work,
    )


def summary(env: dict[str, str]) -> str:
    path = Path(env["GITHUB_STEP_SUMMARY"])
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def test_dry_run_resolves_bump_without_writes(
    release_repo: tuple[Path, Path, dict[str, str], Path],
) -> None:
    work, _bare, env, calls = release_repo
    env["DRY_RUN"] = "true"
    head = _git(work, "rev-parse", "HEAD")

    result = run_bump(work, env)

    assert result.returncode == 0, result.stderr
    assert "dry-run: would open a version bump PR for v1.2.4" in summary(env)
    # A rehearsal writes nothing: no gh calls, no commit, no file edits.
    assert not calls.exists() or calls.read_text(encoding="utf-8") == ""
    assert _git(work, "rev-parse", "HEAD") == head
    assert _git(work, "status", "--porcelain") == ""
    assert 'version = "1.2.3"' in (work / "pyproject.toml").read_text(encoding="utf-8")


def test_dry_run_rejects_version_equal_to_current(
    release_repo: tuple[Path, Path, dict[str, str], Path],
) -> None:
    work, _bare, env, _calls = release_repo
    env["DRY_RUN"] = "true"
    env["SET_VERSION"] = "1.2.3"

    result = run_bump(work, env)

    assert result.returncode != 0
    assert "must be greater than current" in result.stderr


def test_dry_run_existing_tag_fails(
    release_repo: tuple[Path, Path, dict[str, str], Path],
) -> None:
    work, bare, env, _calls = release_repo
    env["DRY_RUN"] = "true"
    _git(bare, "tag", "v1.2.4", _git(bare, "rev-parse", "main"))

    result = run_bump(work, env)

    assert result.returncode == 1
    assert "::error::tag v1.2.4 already exists" in result.stderr


def test_real_bump_pushes_only_bot_branch(
    release_repo: tuple[Path, Path, dict[str, str], Path],
) -> None:
    work, bare, env, calls = release_repo
    original = _git(bare, "rev-parse", "main")
    branch = "bot/release-bump-v1.2.4-4242"

    result = run_bump(work, env)

    assert result.returncode == 0, result.stderr
    head = _git(work, "rev-parse", "HEAD")
    assert head != original
    assert _git(bare, "rev-parse", "main") == original
    assert _git(bare, "rev-parse", branch) == head
    assert _git(bare, "tag") == ""
    assert 'version = "1.2.4"' in (work / "pyproject.toml").read_text(encoding="utf-8")
    commands = calls.read_text(encoding="utf-8").splitlines()
    assert len(commands) == 2
    assert commands[0].startswith("pr list ")
    assert commands[1].startswith(f"pr create --repo {REPOSITORY} --base main --head {branch}")
    assert f"version-bump PR: {PR_URL}" in summary(env)


def test_rerun_reuses_existing_pr(
    release_repo: tuple[Path, Path, dict[str, str], Path],
) -> None:
    work, bare, env, calls = release_repo
    original = _git(bare, "rev-parse", "main")
    env["GH_STUB_EXISTING"] = PR_URL

    result = run_bump(work, env)

    assert result.returncode == 0, result.stderr
    assert _git(work, "rev-parse", "HEAD") == original
    assert _git(bare, "branch", "--list", "bot/*") == ""
    assert calls.read_text(encoding="utf-8").splitlines()[0].startswith("pr list ")
    assert "pr create" not in calls.read_text(encoding="utf-8")
    assert f"version-bump PR: {PR_URL}" in summary(env)


def test_set_version_greater_commits(
    release_repo: tuple[Path, Path, dict[str, str], Path],
) -> None:
    work, _bare, env, _calls = release_repo
    env["SET_VERSION"] = "v2.0.0"

    result = run_bump(work, env)

    assert result.returncode == 0, result.stderr
    assert _git(work, "log", "-1", "--format=%s") == "Release v2.0.0: update version files"


@pytest.mark.parametrize("override", ["01.2.4", "1.03.0", "v1.2.04"])
def test_set_version_rejects_leading_zeroes(
    release_repo: tuple[Path, Path, dict[str, str], Path], override: str
) -> None:
    work, bare, env, calls = release_repo
    head = _git(work, "rev-parse", "HEAD")

    result = run_bump(work, env | {"SET_VERSION": override})

    assert result.returncode != 0
    assert "is not X.Y.Z" in result.stderr
    assert _git(work, "rev-parse", "HEAD") == head
    assert _git(bare, "branch", "--list", "bot/*") == ""
    assert not calls.exists()


def test_release_workflow_delegates_bump_to_script() -> None:
    workflow = (REPO_ROOT / ".github/workflows/release-bump.yml").read_text(encoding="utf-8")
    script = SCRIPT.read_text(encoding="utf-8")
    assert "bash scripts/release_bump.sh" in workflow
    assert "gh pr create" not in workflow
    assert "git ls-remote" not in workflow
    assert "plugins/wire/.plugin/plugin.json" in script
    assert "plugins/wire/skills/*/SKILL.md" in script

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from test_release_bump import REPO_ROOT, _git, make_release_repo  # pyright: ignore[reportPrivateUsage]

PIN = "plugins/wire/skills/wire-workflow/tools-image.json"
LOCK = "docker/image-digests.json"
DIGEST = f"sha256:{'a' * 64}"
PACKAGE = "ghcr.io/vibebb/wire-tools"
TAG = "v1.2.3"


@pytest.fixture
def tagged(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    work, _, env, _ = make_release_repo(tmp_path)
    shutil.copy(REPO_ROOT / "scripts/validate_release_candidate.py", work / "scripts")
    (work / "docker").mkdir()
    entry = {"tag": f"{_git(work, 'rev-parse', 'HEAD')}-tools", "image": PACKAGE, "digest": DIGEST}
    (work / PIN).write_text(json.dumps(entry), encoding="utf-8")
    (work / LOCK).write_text(json.dumps({"wire_tools": entry}), encoding="utf-8")
    _git(work, "add", LOCK, PIN)
    _git(work, "commit", "-m", "merge image lock")
    _git(work, "push", "origin", "main")
    _git(work, "-c", "tag.gpgSign=false", "tag", TAG)
    event = work / "event.json"
    event.write_text('{"deleted":false}', encoding="utf-8")
    gh = Path(env["PATH"].split(":")[0]) / "gh"
    gh.write_text(
        """#!/usr/bin/env bash
set -eu
case "$*" in
  'api --paginate --slurp '*deployment-branch-policies*) printf '%s\n' "$POLICIES" ;;
  'api --paginate --slurp '*'/releases?'*) printf '%s\n' "$RELEASES" ;;
  'api '*'/environments/production') printf '%s\n' "$ENVIRONMENT" ;;
  *) exit 1 ;;
esac
""",
        encoding="utf-8",
    )
    env.update(
        GITHUB_REF_NAME=TAG,
        GITHUB_REF=f"refs/tags/{TAG}",
        GITHUB_SHA=_git(work, "rev-parse", "HEAD"),
        GITHUB_EVENT_PATH=str(event),
        GITHUB_OUTPUT=str(work / "outputs"),
        GITHUB_EVENT_NAME="push",
        ENVIRONMENT=json.dumps(
            {
                "can_admins_bypass": False,
                "deployment_branch_policy": {
                    "protected_branches": False,
                    "custom_branch_policies": True,
                },
                "protection_rules": [{"type": "required_reviewers", "reviewers": [{}]}],
            }
        ),
        POLICIES='[{"branch_policies":[{"type":"tag","name":"v*"}]}]',
        RELEASES="[[]]",
    )
    return work, env


def run(work: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(REPO_ROOT / ".github/scripts/validate_release.sh"), *args],
        cwd=work,
        env=env,
        check=False,
        capture_output=True,
        encoding="utf-8",
    )


@pytest.mark.parametrize("annotated", [False, True])
def test_valid_unsigned_tag(tagged: tuple[Path, dict[str, str]], annotated: bool) -> None:
    work, env = tagged
    if annotated:
        _git(work, "-c", "tag.gpgSign=false", "tag", "-fa", TAG, "-m", TAG)
    result = run(work, env, "--publish-check")
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"image={PACKAGE}@{DIGEST}" in Path(env["GITHUB_OUTPUT"]).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"GITHUB_EVENT_NAME": "pull_request"}, "Expected a v* tag push"),
        ({"GITHUB_REF_NAME": "v1.2.4"}, "Tag name does not match"),
        ({"POLICIES": "null"}, "only the v* tag policy"),
        ({"POLICIES": '[{"branch_policies":[{"type":"branch","name":"main"}]}]'}, "only the v*"),
        ({"ENVIRONMENT": '{"can_admins_bypass":true}'}, "disallow administrator bypass"),
        ({"RELEASES": '[[],[{"tag_name":"v1.2.3","draft":true}]]'}, "no existing Release"),
        ({"RELEASES": '[[{"tag_name":"v1.2.3","draft":false}]]'}, "no existing Release"),
    ],
)
def test_invalid_release_policy(
    tagged: tuple[Path, dict[str, str]], change: dict[str, str], message: str
) -> None:
    work, env = tagged
    result = run(work, env | change, "--publish-check")
    assert result.returncode != 0
    assert message in result.stdout + result.stderr


def move_tag(work: Path, env: dict[str, str], tag: str = TAG) -> None:
    _git(work, "-c", "tag.gpgSign=false", "tag", "-f", tag)
    env.update(
        GITHUB_REF_NAME=tag,
        GITHUB_REF=f"refs/tags/{tag}",
        GITHUB_SHA=_git(work, "rev-parse", "HEAD"),
    )


def test_remote_main_ancestry(tagged: tuple[Path, dict[str, str]]) -> None:
    work, env = tagged
    _git(work, "commit", "--allow-empty", "-m", "off main")
    move_tag(work, env)
    result = run(work, env)
    assert result.returncode != 0
    assert "main history" in result.stderr


@pytest.mark.parametrize(
    ("path", "data", "message"),
    [
        ("src/changed.py", "# changed image input", "candidate image inputs differ"),
        (PIN, "{}", "repository and plugin image pins must agree"),
        ("uv.lock", 'name = "wire-agent"\nversion = "1.2.4"\n', "release version files"),
    ],
)
def test_changed_release_inputs(
    tagged: tuple[Path, dict[str, str]], path: str, data: str, message: str
) -> None:
    work, env = tagged
    changed = work / path
    changed.parent.mkdir(exist_ok=True)
    changed.write_text(data, encoding="utf-8")
    _git(work, "add", path)
    _git(work, "commit", "-m", "modify a release input")
    _git(work, "push", "origin", "main")
    move_tag(work, env)
    result = run(work, env)
    assert result.returncode != 0
    assert message in result.stdout


def test_prevents_latest_rollback(tagged: tuple[Path, dict[str, str]]) -> None:
    work, env = tagged
    _git(work, "-c", "tag.gpgSign=false", "tag", "v1.10.0")
    result = run(work, env, "--publish-check")
    assert result.returncode != 0
    assert "refusing to roll back :latest" in result.stdout


def test_retention_preserves_curated_and_attested_candidates(
    tagged: tuple[Path, dict[str, str]],
) -> None:
    work, env = tagged
    protected_tag = f"{'1' * 40}-tools"
    attested_tag = f"{'2' * 40}-tools"
    orphan_tag = f"{'3' * 40}-tools"
    gh = Path(env["PATH"].split(":")[0]) / "gh"
    gh.write_text(
        f"""#!/usr/bin/env bash
set -eu
case "$*" in
  'api --paginate '*)
    printf '%s\n' \
      $'1\tsha256:curated\t2000-01-01T00:00:00Z\t{protected_tag},v1.2.3,latest' \
      $'2\tsha256:attested\t2000-01-01T00:00:00Z\t{attested_tag}' \
      $'3\tsha256:orphan\t2000-01-01T00:00:00Z\t{orphan_tag}'
    ;;
  *attestations/sha256:attested*) printf '1\n' ;;
  *attestations/sha256:orphan*) printf '0\n' ;;
  *) exit 1 ;;
esac
""",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["bash", str(REPO_ROOT / "scripts/ghcr_orphan_tag_prune.sh")],
        cwd=work,
        env=env | {"GITHUB_REPOSITORY_OWNER": "VibeBB", "GHCR_PRUNE_DRY_RUN": "1"},
        check=False,
        capture_output=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    assert f"keep {protected_tag} (shares a version with a curated tag)" in result.stdout
    assert f"keep {attested_tag} (attestation state: 1)" in result.stdout
    assert f"would delete {orphan_tag}" in result.stdout

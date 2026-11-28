"""Validate the wire release version and the candidate pinned at the Git tag."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import cast

from scripts.bump_version import SEMVER_RE, UV_LOCK, UV_LOCK_RE, BumpError, current_version

PACKAGE = "ghcr.io/vibebb/wire-tools"
INPUTS = (
    ".dockerignore",
    "docker/wire-tools.Dockerfile",
    "pyproject.toml",
    "uv.lock",
    "src",
    "plugins/wire",
    "scripts/e2e_authoring.py",
    "examples",
    ":(exclude)plugins/wire/skills/wire-workflow/tools-image.json",
)


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, encoding="utf-8").strip()


def version_tuple(tag: str) -> tuple[int, ...] | None:
    match = SEMVER_RE.fullmatch(tag[1:]) if tag.startswith("v") else None
    return tuple(map(int, match.groups())) if match else None


def validate(root: Path, tag: str) -> dict[str, str]:
    tagged_version = version_tuple(tag)
    version = current_version(root)
    uv = UV_LOCK_RE.search((root / UV_LOCK).read_text(encoding="utf-8"))
    if tagged_version is None or tag != f"v{version}" or uv is None or uv[2] != version:
        raise ValueError("tag does not match the release version files")
    tags = git(root, "tag", "--list", "v*").splitlines()
    if any(value > tagged_version for other in tags if (value := version_tuple(other))):
        raise ValueError("a newer stable tag exists; refusing to roll back :latest")

    lock = json.loads((root / "docker/image-digests.json").read_text(encoding="utf-8"))
    pin = json.loads(
        (root / "plugins/wire/skills/wire-workflow/tools-image.json").read_text(encoding="utf-8")
    )
    raw_entry = lock["wire_tools"]
    if not isinstance(raw_entry, dict) or pin != raw_entry:
        raise ValueError("the repository and plugin image pins must agree")
    entry = cast("dict[str, object]", raw_entry)
    digest, candidate = entry["digest"], entry["tag"]
    if (
        entry["image"] != PACKAGE
        or not isinstance(digest, str)
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
    ):
        raise ValueError("invalid wire image repository or digest")
    if not isinstance(candidate, str) or not re.fullmatch(r"[0-9a-f]{40}-tools", candidate):
        raise ValueError("wire image pin does not name a SHA-tagged candidate")
    source = candidate.removesuffix("-tools")
    sha = git(root, "rev-parse", "HEAD")
    git(root, "merge-base", "--is-ancestor", source, sha)
    if git(root, "diff", "--name-only", source, sha, "--", *INPUTS):
        raise ValueError("candidate image inputs differ from the tagged commit")
    return {
        "sha": sha,
        "version": version,
        "candidate": f"{PACKAGE}:{candidate}",
        "image": f"{PACKAGE}@{digest}",
    }


def main() -> int:
    try:
        values = validate(Path.cwd(), os.environ["GITHUB_REF_NAME"])
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            for key, value in values.items():
                print(f"{key}={value}", file=output)
    except (
        BumpError,
        ValueError,
        OSError,
        KeyError,
        TypeError,
        subprocess.CalledProcessError,
    ) as exc:
        print(f"::error::Cannot validate release candidate: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

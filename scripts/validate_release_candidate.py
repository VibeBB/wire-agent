"""Resolve and verify the wire tools candidate for a release tag."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from scripts.bump_version import SEMVER_RE, UV_LOCK, UV_LOCK_RE, BumpError, current_version

PACKAGE = "ghcr.io/vibebb/wire-tools"
REPOSITORY = "VibeBB/wire-agent"
PUBLISHER = ".github/workflows/publish-wire-images.yml"
SHA_RE = re.compile(r"[0-9a-f]{40}")
DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")
PIN = Path("plugins/wire/skills/wire-workflow/tools-image.json")
LOCK = Path("docker/image-digests.json")
INPUTS = (
    PUBLISHER,
    ".dockerignore",
    "docker/wire-tools.Dockerfile",
    "pyproject.toml",
    "uv.lock",
    "src",
    "plugins/wire",
    "scripts/e2e_authoring.py",
    "scripts/package_level_sbom.py",
    "examples",
    ":(exclude)plugins/wire/skills/wire-workflow/tools-image.json",
)


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, encoding="utf-8").strip()


def version_tuple(tag: str) -> tuple[int, ...] | None:
    match = SEMVER_RE.fullmatch(tag[1:]) if tag.startswith("v") else None
    return tuple(map(int, match.groups())) if match else None


def inspect(root: Path, source: str) -> str:
    return subprocess.check_output(
        [
            "docker",
            "buildx",
            "imagetools",
            "inspect",
            f"{PACKAGE}:{source}-tools",
            "--format",
            "{{.Manifest.Digest}}",
        ],
        cwd=root,
        encoding="utf-8",
    ).strip()


def verify_source(root: Path, sha: str, source: str) -> None:
    if not SHA_RE.fullmatch(source):
        raise ValueError("invalid candidate source SHA")
    git(root, "merge-base", "--is-ancestor", source, sha)
    if git(root, "diff", "--no-ext-diff", "--name-only", source, sha, "--", *INPUTS):
        raise ValueError("candidate image inputs differ from the tagged commit")


def validate(
    root: Path, tag: str, expected_source: str | None = None, expected_image: str | None = None
) -> dict[str, str]:
    tagged_version = version_tuple(tag)
    version = current_version(root)
    uv = UV_LOCK_RE.search((root / UV_LOCK).read_text(encoding="utf-8"))
    if tagged_version is None or tag != f"v{version}" or uv is None or uv[2] != version:
        raise ValueError("tag does not match the release version files")
    tags = git(root, "tag", "--list", "v*").splitlines()
    if any(value > tagged_version for other in tags if (value := version_tuple(other))):
        raise ValueError("a newer stable tag exists; refusing to roll back :latest")

    sha = git(root, "rev-parse", "HEAD")
    source = expected_source if expected_source is not None else sha
    verify_source(root, sha, source)
    try:
        digest = inspect(root, source)
    except subprocess.CalledProcessError:
        if expected_source is not None:
            raise
        source = git(root, "log", "--first-parent", "-1", "--format=%H", sha, "--", *INPUTS)
        if source == sha:
            raise
        verify_source(root, sha, source)
        digest = inspect(root, source)
    if not DIGEST_RE.fullmatch(digest) or digest == f"sha256:{'0' * 64}":
        raise ValueError("invalid wire image digest")
    image = f"{PACKAGE}@{digest}"
    if expected_image is not None and image != expected_image:
        raise ValueError("the candidate digest changed after validation")
    subprocess.run(
        [
            "gh",
            "attestation",
            "verify",
            f"oci://{image}",
            "--repo",
            REPOSITORY,
            "--signer-workflow",
            f"{REPOSITORY}/{PUBLISHER}",
            "--signer-digest",
            source,
            "--source-digest",
            source,
            "--source-ref",
            "refs/heads/main",
            "--deny-self-hosted-runners",
        ],
        cwd=root,
        check=True,
    )
    return {
        "sha": sha,
        "version": version,
        "source": source,
        "image": image,
    }


def write_locks(root: Path, source: str, image: str) -> None:
    package, _, digest = image.partition("@")
    if package != PACKAGE or not SHA_RE.fullmatch(source) or not DIGEST_RE.fullmatch(digest):
        raise ValueError("invalid validated source or image")
    entry = {
        "image": PACKAGE,
        "digest": digest,
        "tag": f"{source}-tools",
        "attestation": f"https://api.github.com/repos/{REPOSITORY}/attestations/{digest}",
        "dockerfile": "docker/wire-tools.Dockerfile",
    }
    for path, value in ((PIN, entry), (LOCK, {"wire_tools": entry})):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    try:
        if len(sys.argv) == 3 and sys.argv[1] == "--write-locks":
            write_locks(Path(sys.argv[2]), os.environ["CANDIDATE_SOURCE"], os.environ["IMAGE"])
            return 0
        expected_source = expected_image = None
        if sys.argv[1:] == ["--publish-check"]:
            expected_source = os.environ["CANDIDATE_SOURCE"]
            expected_image = os.environ["IMAGE"]
        values = validate(
            Path.cwd(), os.environ["GITHUB_REF_NAME"], expected_source, expected_image
        )
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

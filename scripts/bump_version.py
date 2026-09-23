"""Bump the wire plugin version across every version-bearing file.

Updates plugins/wire/.plugin/plugin.json, pyproject.toml, both SKILL.md
frontmatter lines and the wire-agent package entry in uv.lock. Fails closed
if the four source files disagree on the current version.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")

VERSION_FILES = [
    "plugins/wire/.plugin/plugin.json",
    "pyproject.toml",
    "plugins/wire/skills/wire-connectivity/SKILL.md",
    "plugins/wire/skills/wire-contract/SKILL.md",
    "plugins/wire/skills/wire-gates/SKILL.md",
    "plugins/wire/skills/wire-workflow/SKILL.md",
]

_PATTERNS = {
    "plugins/wire/.plugin/plugin.json": re.compile(r'"version":\s*"([^"]+)"'),
    "pyproject.toml": re.compile(r'(?m)^version = "([^"]+)"'),
    "plugins/wire/skills/wire-connectivity/SKILL.md": re.compile(r"(?m)^version: (.+)$"),
    "plugins/wire/skills/wire-contract/SKILL.md": re.compile(r"(?m)^version: (.+)$"),
    "plugins/wire/skills/wire-gates/SKILL.md": re.compile(r"(?m)^version: (.+)$"),
    "plugins/wire/skills/wire-workflow/SKILL.md": re.compile(r"(?m)^version: (.+)$"),
}

UV_LOCK = "uv.lock"
UV_LOCK_RE = re.compile(r'(?m)^(name = "wire-agent"\nversion = )"([^"]+)"')


class BumpError(Exception):
    pass


def _read_versions(root: Path) -> dict[str, str]:
    versions: dict[str, str] = {}
    for rel, pattern in _PATTERNS.items():
        path = root / rel
        if not path.is_file():
            raise BumpError(f"{rel}: file not found")
        m = pattern.search(path.read_text(encoding="utf-8"))
        if m is None:
            raise BumpError(f"{rel}: version field not found")
        versions[rel] = m.group(1).strip()
    return versions


def _check_consistent(versions: dict[str, str]) -> str:
    current = versions[VERSION_FILES[0]]
    mismatch = {rel: v for rel, v in versions.items() if v != current}
    if mismatch:
        details = "; ".join(f"{rel}={v}" for rel, v in versions.items())
        raise BumpError(f"version mismatch across files: {details}")
    if not SEMVER_RE.match(current):
        raise BumpError(f"current version '{current}' is not X.Y.Z")
    return current


def _bumped(current: str, kind: str) -> str:
    major, minor, patch = (int(x) for x in SEMVER_RE.match(current).groups())  # type: ignore[union-attr]
    if kind == "major":
        return f"{major + 1}.0.0"
    if kind == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def _gt(a: str, b: str) -> bool:
    pa = tuple(int(x) for x in SEMVER_RE.match(a).groups())  # type: ignore[union-attr]
    pb = tuple(int(x) for x in SEMVER_RE.match(b).groups())  # type: ignore[union-attr]
    return pa > pb


def _apply(root: Path, old: str, new: str) -> None:
    for rel, pattern in _PATTERNS.items():
        path = root / rel
        text = path.read_text(encoding="utf-8")
        replaced = pattern.sub(lambda m, v=new: m.group(0).replace(m.group(1), v), text, count=1)
        path.write_text(replaced, encoding="utf-8")
    lock = root / UV_LOCK
    if lock.is_file():
        text = lock.read_text(encoding="utf-8")
        replaced, n = UV_LOCK_RE.subn(rf'\g<1>"{new}"', text, count=1)
        if n != 1:
            raise BumpError(f"{UV_LOCK}: wire-agent package entry not found")
        lock.write_text(replaced, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--bump", choices=["patch", "minor", "major"])
    group.add_argument("--set", dest="set_version", metavar="X.Y.Z")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--github-output", metavar="PATH")
    parser.add_argument(
        "--root",
        default=str(Path(__file__).resolve().parents[1]),
        help="repository root (default: parent of scripts/)",
    )
    args = parser.parse_args(argv)

    root = Path(args.root)
    try:
        current = _check_consistent(_read_versions(root))
        if args.set_version:
            new = args.set_version.lstrip("v")
            if not SEMVER_RE.match(new):
                raise BumpError(f"--set '{new}' is not X.Y.Z")
            if not _gt(new, current):
                raise BumpError(f"--set '{new}' must be greater than current '{current}'")
        else:
            new = _bumped(current, args.bump)
        if not args.dry_run:
            _apply(root, current, new)
    except BumpError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as fh:
            fh.write(f"version={new}\n")
    print(new)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Resolve the wire package and tools image, then exec inside Docker.

Plugin installs update the assets under plugins/wire but do not reinstall
the `wire` Python package, and the host interpreter is not guaranteed to
carry the package dependencies. The launcher therefore runs every wire
module inside the pinned wire-tools image, mounting the resolved source
tree and the workspace so paths stay identical inside the container.

Source resolution order (first directory containing wire/__init__.py wins):
  1. $WIRE_SRC
  2. newest ~/.openhands/cache/extensions/wire-agent-*/src
  3. /opt/wire/src (wire-server image)
  4. <repo>/src when running from a repository checkout
  5. none found -> the image's own baked package is used

Image resolution order (first hit wins):
  1. $WIRE_TOOLS_IMAGE (full ref, e.g. ghcr.io/.../wire-tools@sha256:...)
  2. <plugin>/tools-image.json or repo-cache docker/image-digests.json
     (image + digest, falling back to image + tag)
  3. none resolvable, or the pinned ref cannot be pulled -> error
     (docker-only: the launcher never falls back to a local build)

Usage: mcp_server | prewarm | <wire cli args...>. Any argument other
than mcp_server/prewarm is forwarded to `python -m wire.cli` inside the
container. When `--warn` is present (SessionStart doctor mode), a failed
image resolution prints a warning and exits 0.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

_MODULES = {
    "mcp_server": ("wire.mcp_server",),
}

_CONTAINER_SRC = "/plugin-src"
_ENV_PREFIXES = ("OPENHANDS_", "WIRE_")
_ENV_KEYS = ("HOME", "TMPDIR")


def _candidates(plugin_root: Path) -> list[Path]:
    candidates: list[Path] = []
    env_src = os.environ.get("WIRE_SRC")
    if env_src:
        candidates.append(Path(env_src))
    cache = Path.home() / ".openhands" / "cache" / "extensions"
    try:
        if cache.is_dir():
            candidates.extend(
                sorted(
                    cache.glob("wire-agent-*/src"),
                    key=lambda path: path.stat().st_mtime,
                    reverse=True,
                )
            )
    except OSError:
        pass
    candidates.append(Path("/opt/wire/src"))
    candidates.append(plugin_root.parent.parent / "src")
    return candidates


def resolve_source(plugin_root: Path) -> Path | None:
    for candidate in _candidates(plugin_root):
        try:
            if (candidate / "wire" / "__init__.py").is_file():
                return candidate.resolve()
        except OSError:
            continue
    return None


def _repo_dirs(plugin_root: Path) -> list[Path]:
    """Directories that may carry docker/ build assets for this plugin."""
    dirs: list[Path] = []
    repo_checkout = plugin_root.parent.parent
    if (repo_checkout / "docker").is_dir():
        dirs.append(repo_checkout)
    cache = Path.home() / ".openhands" / "cache" / "extensions"
    try:
        if cache.is_dir():
            dirs.extend(
                sorted(
                    (p for p in cache.glob("wire-agent-*") if p.is_dir()),
                    key=lambda path: path.stat().st_mtime,
                    reverse=True,
                )
            )
    except OSError:
        pass
    return dirs


def _lock_entry_ref(lock_path: Path, key: str | None) -> str | None:
    try:
        data = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    entry = data.get(key) if key else data
    if not isinstance(entry, dict) or not entry.get("image"):
        return None
    if entry.get("digest"):
        return f"{entry['image']}@{entry['digest']}"
    if entry.get("tag"):
        return f"{entry['image']}:{entry['tag']}"
    return None


def _image_from_lock(plugin_root: Path) -> str | None:
    ref = _lock_entry_ref(plugin_root / "tools-image.json", None)
    if ref:
        return ref
    for repo_dir in _repo_dirs(plugin_root):
        ref = _lock_entry_ref(repo_dir / "docker" / "image-digests.json", "wire_tools")
        if ref:
            return ref
    return None


def _docker() -> str | None:
    return shutil.which("docker")


def _ensure_image(plugin_root: Path) -> str:
    """Resolve the pinned tools image ref; fail when none is available."""
    docker = _docker()
    if docker is None:
        raise RuntimeError("docker not found on PATH (wire runs docker-only)")

    ref = os.environ.get("WIRE_TOOLS_IMAGE") or _image_from_lock(plugin_root)
    if ref is None:
        raise RuntimeError(
            "no wire tools image resolvable: set WIRE_TOOLS_IMAGE or pin "
            "image+digest in tools-image.json / docker/image-digests.json"
        )
    if (
        subprocess.run(
            [docker, "image", "inspect", ref],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0
    ):
        return ref
    print(f"wire_launcher: pulling tools image {ref}", file=sys.stderr)
    if (
        subprocess.run(
            [docker, "pull", ref],
            check=False,
            stdout=subprocess.DEVNULL,
        ).returncode
        == 0
    ):
        return ref
    raise RuntimeError(f"wire tools image {ref} not present locally and pull failed")


def _docker_argv(image: str, source: Path | None, inner_argv: list[str]) -> list[str]:
    workdir = os.environ.get("OPENHANDS_PROJECT_DIR") or os.getcwd()
    argv = [
        "docker",
        "run",
        "--rm",
        "-i",
        "--network",
        "none",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "-v",
        f"{workdir}:{workdir}",
        "-w",
        workdir,
    ]
    if source is not None:
        argv += ["-v", f"{source}:{_CONTAINER_SRC}:ro", "-e", f"PYTHONPATH={_CONTAINER_SRC}"]
    for key, value in os.environ.items():
        if key in _ENV_KEYS or any(key.startswith(p) for p in _ENV_PREFIXES):
            argv += ["-e", f"{key}={value}"]
    argv.append(image)
    argv += inner_argv
    return argv


def _warn_or_die(message: str, module_args: list[str]) -> int:
    if "--warn" in module_args:
        print(f"warn: {message}", file=sys.stderr)
        print(json.dumps({"verdict": "fail", "detail": message}))
        return 0
    print(f"wire_launcher: {message}", file=sys.stderr)
    return 1


def main() -> int:
    argv = sys.argv[1:]
    if not argv:
        print("usage: wire_launcher.py {mcp_server|prewarm|<wire cli args...>}", file=sys.stderr)
        return 2

    plugin_root = Path(__file__).resolve().parents[1]
    try:
        image = _ensure_image(plugin_root)
    except RuntimeError as exc:
        return _warn_or_die(str(exc), argv)
    if argv[0] == "prewarm":
        print(f"wire_launcher: tools image ready: {image}")
        return 0

    source = resolve_source(plugin_root)
    if argv[0] in _MODULES:
        inner = ["python", "-m", _MODULES[argv[0]], *argv[1:]]
    else:
        inner = ["python", "-m", "wire.cli", *argv]
    os.execvp("docker", _docker_argv(image, source, inner))
    return 0


if __name__ == "__main__":
    sys.exit(main())

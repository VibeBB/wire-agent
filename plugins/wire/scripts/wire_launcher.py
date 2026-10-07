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

The OpenHands cache candidates are searched under both $HOME and the
account's real home directory: callers sometimes override HOME for the
tools container (the image runs as the host uid and its baked-in home is
not writable), and a redirected HOME must not blind the cache lookup.

Image resolution order (first hit wins):
  1. $WIRE_TOOLS_IMAGE (full ref, e.g. ghcr.io/.../wire-tools@sha256:...)
  2. <plugin>/tools-image.json or <plugin>/skills/*/tools-image.json or
     repo-cache docker/image-digests.json
     (image + digest, falling back to image + tag)
  3. none resolvable, or the pinned ref cannot be pulled -> error
     (docker-only: the launcher never falls back to a local build)

Usage: mcp_server | prewarm | <wire cli args...>. Any argument other
than mcp_server/prewarm is forwarded to `python -m wire.cli` inside the
container. When `--warn` is present (SessionStart doctor mode), a failed
image resolution prints a warning and exits 0.

Launcher-side verification uses WIRE_VERIFY_ATTESTATION=auto|require|off.
It verifies lock provenance before pulls and on every prewarm; normal use
does not re-verify an image that is already present locally.
"""

from __future__ import annotations

import contextlib
import json
import os
import pwd
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, TypedDict, cast

_MODULES = {
    "mcp_server": "wire.mcp_server",
}

_CONTAINER_SRC = "/plugin-src"
_ENV_PREFIXES = ("OPENHANDS_", "WIRE_")
_ENV_KEYS = ("TMPDIR",)
_INSPECT_TIMEOUT_S = 30
_PULL_TIMEOUT_S = 900
_ATTEST_TIMEOUT_S = 120
_GH_AUTH_TIMEOUT_S = 15
_DOCKER_INFO_TIMEOUT_S = 10
_VERIFY_ENV = "WIRE_VERIFY_ATTESTATION"
_REPOSITORY = "VibeBB/wire-agent"
_PUBLISH_FILE = ".github/workflows/publish-wire-images.yml"


class ImagePin(TypedDict):
    ref: str
    image: str | None
    digest: str | None
    attestation: str | None


# The container runs as the host uid, whose passwd entry and home do not
# exist inside the image: a forwarded HOME/XDG leaves fontconfig, ezdxf and
# friends without writable directories. Point the transient state at /tmp.
_CONTAINER_ENV = {
    "HOME": "/tmp",
    "TMPDIR": "/tmp",
    "XDG_CACHE_HOME": "/tmp/.cache",
    "XDG_CONFIG_HOME": "/tmp/.config",
    "XDG_DATA_HOME": "/tmp/.local/share",
}


def _homes() -> list[Path]:
    """$HOME first, then the account's real home (HOME may be overridden)."""
    homes = [Path.home()]
    try:
        real = Path(pwd.getpwuid(os.getuid()).pw_dir)
    except (KeyError, OSError):
        return homes
    if real != homes[0]:
        homes.append(real)
    return homes


def _candidates(plugin_root: Path) -> list[Path]:
    candidates: list[Path] = []
    env_src = os.environ.get("WIRE_SRC")
    if env_src:
        candidates.append(Path(env_src))
    for home in _homes():
        cache = home / ".openhands" / "cache" / "extensions"
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
    for home in _homes():
        cache = home / ".openhands" / "cache" / "extensions"
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


def _lock_entry_ref(lock_path: Path, key: str | None) -> ImagePin | None:
    try:
        data: Any = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    data = cast(dict[str, Any], data)
    entry = data.get(key) if key else data
    if not isinstance(entry, dict):
        return None
    entry = cast(dict[str, Any], entry)
    image = entry.get("image")
    if not isinstance(image, str) or not image:
        return None
    digest = entry.get("digest")
    digest = digest if isinstance(digest, str) and digest else None
    tag = entry.get("tag")
    tag = tag if isinstance(tag, str) and tag else None
    if digest is None and tag is None:
        return None
    attestation = entry.get("attestation")
    return {
        "ref": f"{image}@{digest}" if digest else f"{image}:{tag}",
        "image": image,
        "digest": digest,
        "attestation": attestation if isinstance(attestation, str) and attestation else None,
    }


def _image_from_lock(plugin_root: Path) -> ImagePin | None:
    pin = _lock_entry_ref(plugin_root / "tools-image.json", None)
    if pin:
        return pin
    try:
        skill_pins = sorted(plugin_root.glob("skills/*/tools-image.json"))
    except OSError:
        skill_pins = []
    for pin in skill_pins:
        lock_pin = _lock_entry_ref(pin, None)
        if lock_pin:
            return lock_pin
    for repo_dir in _repo_dirs(plugin_root):
        lock_pin = _lock_entry_ref(repo_dir / "docker" / "image-digests.json", "wire_tools")
        if lock_pin:
            return lock_pin
    return None


def _docker() -> str | None:
    return shutil.which("docker")


def _inside_conversation_container() -> bool:
    """True when running inside an OpenHands docker conversation runtime.

    The runtime injects ``OH_PERSISTENCE_DIR``/``OH_RUNTIME_LAUNCHED_PROFILE``
    into each ``agent-server-conversation-*`` container, which carries no
    docker client — wire tools then have nowhere to launch the pinned
    tools image. ``OH_CONVERSATION_RUNTIME`` is not usable as the signal:
    the runtime sets it to ``local`` inside the container itself.
    """
    if os.environ.get("OH_PERSISTENCE_DIR") or os.environ.get("OH_RUNTIME_LAUNCHED_PROFILE"):
        return True
    with contextlib.suppress(OSError):
        return Path.home() == Path("/var/openhands/.openhands")
    return False


def _attestation_mode() -> str:
    mode = os.environ.get(_VERIFY_ENV, "auto")
    if mode not in {"auto", "require", "off"}:
        raise ValueError(
            f"{_VERIFY_ENV} must be auto, require, or off (got {mode!r}); "
            f"usage: {_VERIFY_ENV}=auto|require|off"
        )
    return mode


def _run_timed(
    command: list[str],
    operation: str,
    timeout: int,
    **kwargs: Any,
) -> subprocess.CompletedProcess[str]:
    try:
        return cast(
            subprocess.CompletedProcess[str],
            subprocess.run(command, timeout=timeout, **kwargs),
        )
    except OSError as exc:
        raise RuntimeError(f"{operation} failed: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{operation} timed out after {timeout}s") from exc


def _verify_attestation(pin: ImagePin, *, override: bool) -> None:
    mode = _attestation_mode()
    if mode == "off":
        return
    reason: str | None = None
    gh = shutil.which("gh")
    if override:
        reason = "tools image override has no lock attestation context"
    elif not pin["attestation"]:
        reason = "lock entry has no attestation"
    elif not pin["image"] or not pin["digest"]:
        reason = "lock entry has no digest"
    elif gh is None:
        reason = "gh is not on PATH"
    else:
        try:
            auth = _run_timed(
                [gh, "auth", "status"],
                "gh auth status",
                _GH_AUTH_TIMEOUT_S,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except RuntimeError:
            reason = "gh auth status failed"
        else:
            if auth.returncode != 0:
                reason = "gh auth status failed"
    if reason is not None:
        if mode == "require":
            raise RuntimeError(f"attestation verification required but {reason}")
        print(f"wire_launcher: attestation verification skipped: {reason}", file=sys.stderr)
        return
    assert gh is not None
    assert pin["image"] is not None and pin["digest"] is not None
    result = _run_timed(
        [
            gh,
            "attestation",
            "verify",
            f"oci://{pin['image']}@{pin['digest']}",
            "--repo",
            _REPOSITORY,
            "--signer-workflow",
            f"{_REPOSITORY}/{_PUBLISH_FILE}",
        ],
        "gh attestation verify",
        _ATTEST_TIMEOUT_S,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"attestation verification failed for {pin['image']}@{pin['digest']}")


def _ensure_image(plugin_root: Path, *, pull: bool = True, prewarm: bool = False) -> str:
    """Resolve the pinned tools image ref; fail when none is available.

    ``pull=False`` reports a missing local image without pulling it — the
    SessionStart doctor hook (--warn) must stay lightweight."""
    docker = _docker()
    if docker is None:
        detail = "docker not found on PATH (wire runs docker-only)"
        if _inside_conversation_container():
            detail += (
                " — this appears to be an OpenHands docker conversation "
                "container, which cannot launch tool containers; set the "
                "conversation runtime to local (Agent Canvas -> Settings -> "
                "Application) and start a new conversation"
            )
        raise RuntimeError(detail)

    override_ref = os.environ.get("WIRE_TOOLS_IMAGE")
    if override_ref:
        pin: ImagePin | None = {
            "ref": override_ref,
            "image": None,
            "digest": None,
            "attestation": None,
        }
    else:
        pin = _image_from_lock(plugin_root)
    if pin is None:
        raise RuntimeError(
            "no wire tools image resolvable: set WIRE_TOOLS_IMAGE or pin "
            "image+digest in tools-image.json / docker/image-digests.json"
        )
    ref = pin["ref"]
    if prewarm:
        _verify_attestation(pin, override=bool(override_ref))
    try:
        inspect_result = subprocess.run(
            [docker, "image", "inspect", ref],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=_INSPECT_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"docker image inspect timed out after {_INSPECT_TIMEOUT_S} seconds"
        ) from exc
    if inspect_result.returncode == 0:
        return ref
    if not pull:
        raise RuntimeError(
            f"wire tools image {ref} not pulled locally; run 'wire_launcher.py prewarm' to fetch it"
        )
    if not prewarm:
        _verify_attestation(pin, override=bool(override_ref))
    print(f"wire_launcher: pulling tools image {ref}", file=sys.stderr)
    try:
        pull_result = subprocess.run(
            [docker, "pull", ref],
            check=False,
            stdout=subprocess.DEVNULL,
            timeout=_PULL_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"docker pull timed out after {_PULL_TIMEOUT_S} seconds") from exc
    if pull_result.returncode == 0:
        return ref
    raise RuntimeError(f"wire tools image {ref} not present locally and pull failed")


def _docker_info_security_options() -> str | None:
    """Return `docker info` security options, or None when unavailable."""
    docker = _docker()
    if docker is None:
        return None
    try:
        result = subprocess.run(
            [docker, "info", "-f", "{{json .SecurityOptions}}"],
            capture_output=True,
            text=True,
            timeout=_DOCKER_INFO_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def _container_user() -> str:
    """uid:gid to run the tools container as.

    On rootless Docker the host uid maps to an unmapped subuid inside the
    container user namespace, so bind-mounted workspace writes fail. There
    container root (0:0) maps back to the daemon's owner — the invoking
    user — so 0:0 keeps writes working without weakening isolation (the
    container stays read-only/cap-dropped). On rootful Docker keep the host
    uid so artifacts stay user-owned.
    """
    if "name=rootless" in (_docker_info_security_options() or ""):
        return "0:0"
    return f"{os.getuid()}:{os.getgid()}"


def _docker_argv(image: str, source: Path | None, inner_argv: list[str]) -> list[str]:
    workdir = os.environ.get("OPENHANDS_PROJECT_DIR") or os.getcwd()
    argv = [
        "docker",
        "run",
        "--rm",
        "-i",
        "--network",
        "none",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--user",
        _container_user(),
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
    for key, value in _CONTAINER_ENV.items():
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

    try:
        _attestation_mode()
    except ValueError as exc:
        print(f"wire_launcher: {exc}", file=sys.stderr)
        return 2

    plugin_root = Path(__file__).resolve().parents[1]
    try:
        if argv[0] == "prewarm":
            image = _ensure_image(plugin_root, pull="--warn" not in argv, prewarm=True)
        else:
            image = _ensure_image(plugin_root, pull="--warn" not in argv)
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

#!/usr/bin/env python3
"""Run a command inside the digest-pinned wire-tools image.

Resolves the image ref from ``docker/image-digests.json`` (same lock the
publish workflow writes), pulls it when absent, then ``docker run``s the
given command with the repository bind-mounted at its own path so file
paths stay identical inside and outside the container.

Environment notes:

- ``PYTHONPATH=<repo>/src`` so the checkout's ``wire`` package wins over the
  image's baked copy.
- ``HOME=/tmp`` and ``UV_PROJECT_ENVIRONMENT=/tmp/image-venv`` give ``uv
  run`` a writable, disposable project env inside the container when the
  invoked command needs dev dependencies (e.g. pytest) — the image itself
  ships runtime deps only.
- ``--user <uid>:<gid>`` keeps files created in the mounted checkout owned
  by the invoking user (``0:0`` under rootless Docker, where the host uid
  maps to an unusable subuid and container root maps back to the daemon's
  owner — the invoking user).

Usage::

    python scripts/run_in_locked_image.py -- python scripts/e2e_authoring.py \
        --contract examples/sensor-harness/sensor-harness.contract.json --out out/x
    python scripts/run_in_locked_image.py --entry wire_tools --no-pull -- python -m wire doctor

Exit code is the container's exit code.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from .print_locked_image import locked_image
except ImportError:
    from print_locked_image import locked_image

ROOT = Path(__file__).resolve().parent.parent

_DOCKER_INFO_TIMEOUT_S = 10


def _docker_info_security_options() -> str | None:
    """Return `docker info` security options, or None when unavailable."""
    try:
        result = subprocess.run(
            ["docker", "info", "-f", "{{json .SecurityOptions}}"],
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
    user — so 0:0 keeps writes working. On rootful Docker keep the host
    uid so artifacts stay user-owned.
    """
    if "name=rootless" in (_docker_info_security_options() or ""):
        return "0:0"
    return f"{os.getuid()}:{os.getgid()}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=ROOT / "docker" / "image-digests.json")
    parser.add_argument("--entry", default="wire_tools")
    parser.add_argument("--no-pull", action="store_true", help="fail instead of pulling")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="command after --")
    args = parser.parse_args(argv)

    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print("usage: run_in_locked_image.py [--entry NAME] [--no-pull] -- <argv...>")
        return 2

    docker = shutil.which("docker")
    if docker is None:
        print("FAIL: docker not found on PATH")
        return 1
    try:
        image = locked_image(args.lock, args.entry)
    except ValueError as exc:
        print(f"FAIL: {exc}")
        return 1

    present = (
        subprocess.run(
            [docker, "image", "inspect", image],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0
    )
    if not present:
        if args.no_pull:
            print(f"FAIL: image not present locally: {image}")
            return 1
        print(f"run_in_locked_image: pulling {image}", file=sys.stderr)
        if subprocess.run([docker, "pull", image], check=False).returncode != 0:
            print(f"FAIL: docker pull failed for {image}")
            return 1

    run_argv = [
        docker,
        "run",
        "--rm",
        "--user",
        _container_user(),
        "-e",
        "HOME=/tmp",
        "-e",
        "UV_PROJECT_ENVIRONMENT=/tmp/image-venv",
        "-e",
        f"PYTHONPATH={ROOT}/src",
        "-v",
        f"{ROOT}:{ROOT}",
        "-w",
        str(ROOT),
        image,
        *command,
    ]
    return subprocess.run(run_argv, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())

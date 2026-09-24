"""Run the canonical repository verification stages.

Commands declared `barrier=True` always run alone in declaration order;
consecutive non-barrier commands run in parallel up to `--jobs` workers.
The parallelism degree never changes the artifacts produced by the commands.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@dataclass(frozen=True)
class Command:
    argv: tuple[str, ...]
    barrier: bool = False


STAGES: dict[str, tuple[Command, ...]] = {
    "docs": (
        Command(("uv", "run", "python", "scripts/verify_docs.py")),
        Command(("git", "diff", "--check")),
    ),
    "fast": (
        Command(("uv", "sync", "--locked"), barrier=True),
        Command(("uv", "run", "ruff", "check", ".")),
        Command(("uv", "run", "ruff", "format", "--check", ".")),
        Command(("uv", "run", "pyright")),
        Command(("uv", "run", "pytest")),
        Command(("uv", "run", "python", "scripts/verify_docs.py")),
        Command(("git", "diff", "--check")),
    ),
    "standard": (
        Command(("uv", "sync", "--locked"), barrier=True),
        Command(("uv", "run", "ruff", "check", ".")),
        Command(("uv", "run", "ruff", "format", "--check", ".")),
        Command(("uv", "run", "pyright")),
        Command(("uv", "run", "pytest")),
        Command(("uv", "run", "python", "scripts/check_plugin_load.py")),
        # e2e runs inside the digest-pinned wire-tools image (drawio-desktop
        # lives there); the checkout is bind-mounted so it exercises the
        # working tree's code.
        Command(
            (
                "uv",
                "run",
                "python",
                "scripts/run_in_locked_image.py",
                "--",
                "python",
                "scripts/e2e_authoring.py",
                "--contract",
                "examples/sensor-harness/sensor-harness.contract.json",
                "--out",
                "out/sensor-harness",
            )
        ),
        Command(("uv", "run", "python", "scripts/verify_docs.py")),
        Command(("git", "diff", "--check")),
    ),
    "drawio": (
        Command(("uv", "sync", "--locked"), barrier=True),
        Command(
            (
                "uv",
                "run",
                "python",
                "scripts/run_in_locked_image.py",
                "--",
                "python",
                "scripts/check_drawio_export.py",
            )
        ),
    ),
}


def _run_one(command: Command) -> tuple[Command, int, str]:
    print("$ " + " ".join(command.argv), flush=True)
    proc = subprocess.run(command.argv, cwd=ROOT, capture_output=True, text=True, check=False)
    return command, proc.returncode, proc.stdout + proc.stderr


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=tuple(STAGES), default="fast")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--jobs", type=int, default=min(os.cpu_count() or 1, 4))
    args = parser.parse_args(argv)
    commands = STAGES[args.stage]
    if args.list:
        print(
            json.dumps(
                {
                    stage: [{"command": list(c.argv), "barrier": c.barrier} for c in stage_commands]
                    for stage, stage_commands in STAGES.items()
                },
                indent=2,
            )
        )
        return 0
    if args.jobs <= 1:
        for command in commands:
            print("$ " + " ".join(command.argv), flush=True)
            result = subprocess.run(command.argv, cwd=ROOT, check=False)
            if result.returncode:
                return result.returncode
        return 0

    index = 0
    failures: list[Command] = []
    while index < len(commands):
        command = commands[index]
        if command.barrier:
            _, code, output = _run_one(command)
            sys.stdout.write(output)
            sys.stdout.flush()
            if code:
                failures.append(command)
                break
            index += 1
            continue
        group: list[Command] = []
        while index < len(commands) and not commands[index].barrier:
            group.append(commands[index])
            index += 1
        results: dict[int, tuple[Command, int, str]] = {}
        with ThreadPoolExecutor(max_workers=min(args.jobs, len(group))) as pool:
            futures = {pool.submit(_run_one, c): i for i, c in enumerate(group)}
            for future in futures:
                i = futures[future]
                results[i] = future.result()
        for i in sorted(results):
            _, code, output = results[i]
            sys.stdout.write(output)
            sys.stdout.flush()
            if code:
                failures.append(results[i][0])
    if failures:
        for command in failures:
            print("FAILED: " + " ".join(command.argv), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

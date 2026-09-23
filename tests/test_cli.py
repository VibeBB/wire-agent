"""CLI surface tests (exit codes and advisory flags)."""

from __future__ import annotations

import subprocess
import sys


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "wire", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_doctor_passes() -> None:
    result = _run("doctor")
    assert result.returncode == 0, result.stdout + result.stderr


def test_doctor_warn_exits_zero() -> None:
    """`doctor --warn` is advisory: it must not fail a SessionStart hook."""
    result = _run("doctor", "--warn")
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"verdict"' in result.stdout


def test_doctor_warn_on_missing_flag_peer() -> None:
    """Unknown flags still fail argument parsing (fail-closed)."""
    result = _run("doctor", "--definitely-not-a-flag")
    assert result.returncode != 0

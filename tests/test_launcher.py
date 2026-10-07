"""wire_launcher.py behavior checks (no docker required — argv/lock only)."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1] / "plugins" / "wire"
LAUNCHER = PLUGIN_ROOT / "scripts" / "wire_launcher.py"


def _load_launcher() -> ModuleType:
    spec = importlib.util.spec_from_file_location("wire_launcher_test", LAUNCHER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_plugin_image_pin_ships_with_plugin() -> None:
    pin = PLUGIN_ROOT / "skills" / "wire-workflow" / "tools-image.json"
    assert pin.is_file()
    data = json.loads(pin.read_text(encoding="utf-8"))
    assert data["image"].endswith("/wire-tools")
    assert data["digest"].startswith("sha256:")
    assert data["tag"]
    assert data["published_at"]
    assert data["tools"]["python"]


def test_plugin_image_pin_matches_docker_lock() -> None:
    pin = PLUGIN_ROOT / "skills" / "wire-workflow" / "tools-image.json"
    lock = Path(__file__).resolve().parents[1] / "docker" / "image-digests.json"
    if not lock.is_file():
        pytest.skip("docker/image-digests.json not in checkout")
    pinned = json.loads(pin.read_text(encoding="utf-8"))
    locked = json.loads(lock.read_text(encoding="utf-8"))["wire_tools"]
    assert pinned["image"] == locked["image"]
    assert pinned["digest"] == locked["digest"]


def test_docker_argv_transient_state_env() -> None:
    """HOME/XDG point at /tmp inside the container (host HOME is unwritable)."""
    module = _load_launcher()
    argv = module._docker_argv(image="img", source=None, inner_argv=["doctor"])
    env = {
        argv[i + 1].split("=", 1)[0]: argv[i + 1].split("=", 1)[1]
        for i, arg in enumerate(argv)
        if arg == "-e"
    }
    assert env["HOME"] == "/tmp"
    assert env["XDG_CACHE_HOME"].startswith("/tmp/")
    assert env["XDG_CONFIG_HOME"].startswith("/tmp/")
    assert env["XDG_DATA_HOME"].startswith("/tmp/")


def test_docker_argv_does_not_forward_host_home(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", "/home/somebody")
    module = _load_launcher()
    argv = module._docker_argv(image="img", source=None, inner_argv=["doctor"])
    env_pairs = [argv[i + 1] for i, arg in enumerate(argv) if arg == "-e"]
    assert not any(pair == "HOME=/home/somebody" for pair in env_pairs)


def test_docker_argv_forwards_project_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENHANDS_PROJECT_DIR", str(tmp_path))
    module = _load_launcher()
    argv = module._docker_argv(image="img", source=None, inner_argv=["mcp_server"])
    env_pairs = [argv[i + 1] for i, arg in enumerate(argv) if arg == "-e"]
    assert f"OPENHANDS_PROJECT_DIR={tmp_path}" in env_pairs
    assert argv[argv.index("-w") + 1] == str(tmp_path)


def test_image_from_lock_reads_skill_pin(tmp_path: Path) -> None:
    module = _load_launcher()
    skill_dir = tmp_path / "skills" / "wire-workflow"
    skill_dir.mkdir(parents=True)
    entry = {
        "image": "ghcr.io/x/wire-tools",
        "digest": "sha256:abc",
        "tag": "t1",
        "attestation": "https://github.com/VibeBB/wire-agent/attestations/example",
    }
    (skill_dir / "tools-image.json").write_text(json.dumps(entry), encoding="utf-8")
    assert module._image_from_lock(tmp_path) == {
        "ref": "ghcr.io/x/wire-tools@sha256:abc",
        "image": "ghcr.io/x/wire-tools",
        "digest": "sha256:abc",
        "attestation": "https://github.com/VibeBB/wire-agent/attestations/example",
    }


def test_ensure_image_warn_mode_never_pulls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """pull=False must report failure without running docker pull."""
    monkeypatch.delenv("WIRE_TOOLS_IMAGE", raising=False)
    module = _load_launcher()
    # Point resolution at a pin whose image cannot exist locally.
    skill_dir = tmp_path / "skills" / "wire-workflow"
    skill_dir.mkdir(parents=True)
    (skill_dir / "tools-image.json").write_text(
        json.dumps({"image": "ghcr.io/x/definitely-not-pulled", "digest": "sha256:abc"}),
        encoding="utf-8",
    )
    if module._docker() is None:
        pytest.skip("docker not on PATH")
    with pytest.raises(RuntimeError, match="not pulled locally"):
        module._ensure_image(tmp_path, pull=False)


def test_inspect_timeout_fails_without_falling_through_to_pull(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ref = "ghcr.io/x/wire-tools@sha256:abc"
    monkeypatch.delenv("WIRE_TOOLS_IMAGE", raising=False)
    (tmp_path / "tools-image.json").write_text(
        json.dumps({"image": "ghcr.io/x/wire-tools", "digest": "sha256:abc"}),
        encoding="utf-8",
    )
    module = _load_launcher()
    monkeypatch.setattr(module, "_docker", lambda: "docker")
    calls: list[tuple[list[str], float | None]] = []

    def timeout_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        timeout = kwargs["timeout"]
        calls.append((args, timeout))
        raise subprocess.TimeoutExpired(args, timeout)

    monkeypatch.setattr(module.subprocess, "run", timeout_run)
    with pytest.raises(RuntimeError, match="docker image inspect timed out after 30 seconds"):
        module._ensure_image(tmp_path)
    assert calls == [(["docker", "image", "inspect", ref], 30)]


def test_pull_timeout_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ref = "ghcr.io/x/wire-tools@sha256:abc"
    monkeypatch.delenv("WIRE_TOOLS_IMAGE", raising=False)
    (tmp_path / "tools-image.json").write_text(
        json.dumps({"image": "ghcr.io/x/wire-tools", "digest": "sha256:abc"}),
        encoding="utf-8",
    )
    module = _load_launcher()
    monkeypatch.setattr(module, "_docker", lambda: "docker")
    calls: list[tuple[list[str], float | None]] = []

    def timeout_pull(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        timeout = kwargs["timeout"]
        calls.append((args, timeout))
        if args[1:3] == ["image", "inspect"]:
            return subprocess.CompletedProcess(args, 1)
        raise subprocess.TimeoutExpired(args, timeout)

    monkeypatch.setattr(module.subprocess, "run", timeout_pull)
    with pytest.raises(RuntimeError, match="docker pull timed out after 900 seconds"):
        module._ensure_image(tmp_path)
    assert calls == [
        (["docker", "image", "inspect", ref], 30),
        (["docker", "pull", ref], 900),
    ]


def test_homes_includes_real_pw_dir() -> None:
    module = _load_launcher()
    import pwd as _pwd

    homes = module._homes()
    assert Path.home() in homes
    assert Path(_pwd.getpwuid(os.getuid()).pw_dir) in homes


def test_container_user_rootless(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rootless daemons get 0:0 — the host uid maps to an unusable subuid."""
    module = _load_launcher()
    monkeypatch.setattr(
        module,
        "_docker_info_security_options",
        lambda: '["name=seccomp,profile=builtin","name=rootless","name=cgroupns"]',
    )
    assert module._container_user() == "0:0"
    argv = module._docker_argv(image="img", source=None, inner_argv=["doctor"])
    assert argv[argv.index("--user") + 1] == "0:0"


def test_container_user_rootful(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rootful daemons keep the invoking uid:gid so artifacts stay user-owned."""
    module = _load_launcher()
    monkeypatch.setattr(
        module,
        "_docker_info_security_options",
        lambda: '["name=seccomp,profile=builtin"]',
    )
    assert module._container_user() == f"{os.getuid()}:{os.getgid()}"


def test_container_user_docker_info_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """docker absent/failing -> keep the current uid:gid behavior."""
    module = _load_launcher()
    monkeypatch.setattr(module, "_docker_info_security_options", lambda: None)
    assert module._container_user() == f"{os.getuid()}:{os.getgid()}"


def test_run_in_locked_image_container_user(monkeypatch: pytest.MonkeyPatch) -> None:
    """scripts/run_in_locked_image.py shares the same rootless rule."""
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.setattr(sys, "path", [str(repo_root / "scripts"), *sys.path])
    spec = importlib.util.spec_from_file_location(
        "run_in_locked_image_test", repo_root / "scripts" / "run_in_locked_image.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_docker_info_security_options", lambda: '["name=rootless"]')
    assert module._container_user() == "0:0"
    monkeypatch.setattr(module, "_docker_info_security_options", lambda: None)
    assert module._container_user() == f"{os.getuid()}:{os.getgid()}"


def test_main_mcp_server_argv_is_module_string(monkeypatch: pytest.MonkeyPatch) -> None:
    """`mcp_server` must exec `python -m wire.mcp_server`; every argv entry is a str."""
    module = _load_launcher()
    captured: list[list[str]] = []

    def fake_execvp(file: str, args: list[str]) -> None:
        captured.append([file, *args])

    def fake_ensure_image(_root: Path, *, pull: bool = True) -> str:
        return "img@sha256:abc"

    def fake_resolve_source(_root: Path) -> Path | None:
        return None

    monkeypatch.setattr(module, "_ensure_image", fake_ensure_image)
    monkeypatch.setattr(module, "resolve_source", fake_resolve_source)
    monkeypatch.setattr(os, "execvp", fake_execvp)
    monkeypatch.setattr(sys, "argv", ["wire_launcher.py", "mcp_server", "--extra"])
    assert module.main() == 0
    assert len(captured) == 1
    argv = captured[0]
    assert argv[0] == "docker"
    assert all(isinstance(arg, str) for arg in argv)
    assert argv[-4:] == ["python", "-m", "wire.mcp_server", "--extra"]


def test_warn_fallback_json_matches_doctor_key(capsys: pytest.CaptureFixture[str]) -> None:
    """The --warn fallback payload uses the same top-level key as wire.doctor."""
    module = _load_launcher()
    assert module._warn_or_die("boom", ["doctor", "--warn"]) == 0
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload == {"verdict": "fail", "detail": "boom"}

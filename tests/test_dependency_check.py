from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path

import pytest
import scripts.check_dependency_updates as check_dependency_updates_module
from scripts.check_dependency_updates import (
    HTTP_TIMEOUT_SECONDS,
    ROOT,
    SUBPROCESS_TIMEOUT_SECONDS,
    DependencyDeferral,
    DependencyStatus,
    _github_latest_tag,  # pyright: ignore[reportPrivateUsage]
    apply_deferrals,
    check_docker_args,
    check_git_clones,
    dependency_names,
    docker_arg_pins,
    docker_base_image,
    lock_versions,
    main,
    project_data,
    render_markdown,
    uv_version_pin,
    workflow_files,
)


def test_project_dependencies_parsed():
    deps = dependency_names(project_data(ROOT))
    assert "pydantic" in deps
    assert "openhands-sdk" in deps
    assert "mcp" in deps
    assert "pytest" in deps


def test_lock_versions_cover_direct_deps():
    versions = lock_versions(ROOT)
    deps = dependency_names(project_data(ROOT))
    missing = [name for name in deps if name not in versions]
    assert missing == []
    assert versions["openhands-sdk"] == "1.50.1"


def test_uv_pin_parsed():
    assert uv_version_pin(ROOT) == "==0.12.21"


def test_workflow_files_have_expected_suffixes():
    files = workflow_files(ROOT)
    assert all(f.suffix in {".yml", ".yaml"} for f in files)


def test_docker_arg_pins_parsed():
    args = docker_arg_pins(ROOT)
    assert args["UV_VERSION"] == "0.12.21"


def test_docker_arg_matches_uv_pin():
    args = docker_arg_pins(ROOT)
    assert f"=={args['UV_VERSION']}" == uv_version_pin(ROOT)


def test_docker_base_image_parsed():
    base = docker_base_image(ROOT)
    assert base == ("debian", "13-slim")


def test_lynis_clone_pin_parsed():
    statuses = check_git_clones(ROOT, list_remote_tags=lambda url: ["3.1.7"])
    lynis = next(status for status in statuses if status.name == "CISOfy/lynis")
    assert lynis.current == "3.1.7"
    assert lynis.latest == "3.1.7"
    assert lynis.outdated is False


def test_git_clones_report_outdated_and_fetch_failed():
    statuses = check_git_clones(ROOT, list_remote_tags=lambda url: ["3.1.7", "3.2.0"])
    lynis = next(status for status in statuses if status.name == "CISOfy/lynis")
    assert lynis.latest == "3.2.0"
    assert lynis.outdated is True

    def failed_tags(url: str) -> list[str]:
        raise OSError(url)

    statuses = check_git_clones(ROOT, list_remote_tags=failed_tags)
    lynis = next(status for status in statuses if status.name == "CISOfy/lynis")
    assert lynis.latest == "?"
    assert lynis.fetch_failed is True
    assert lynis.outdated is False


def test_render_markdown_groups_by_surface():
    statuses = [
        DependencyStatus("pypi", "pydantic", "2.13.5", "2.13.5", "pyproject.toml", False),
        DependencyStatus("pypi", "mcp", "1.30.0", "2.2.0", "pyproject.toml", True),
        DependencyStatus(
            "docker-base", "debian", "13-slim", "13-slim", "docker/wire-tools.Dockerfile", False
        ),
    ]
    markdown = render_markdown(statuses)
    assert "## PyPI (direct dependencies)" in markdown
    assert "## Docker base image" in markdown
    assert "| mcp | 1.30.0 | 2.2.0 | update available | pyproject.toml |" in markdown
    assert "| pydantic | 2.13.5 | 2.13.5 | up to date | pyproject.toml |" in markdown
    assert "update candidates: 1" in markdown


def test_apply_deferrals_marks_matching_outdated(tmp_path: Path):
    deferrals_path = tmp_path / "scripts" / "dependency_update_deferrals.json"
    deferrals_path.parent.mkdir(parents=True)
    deferrals_path.write_text(
        json.dumps(
            {
                "deferrals": [
                    {
                        "surface": "pypi",
                        "name": "mcp",
                        "latest": "2.2.0",
                        "review_by": "2999-01-01",
                        "reason": "test",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    from scripts.check_dependency_updates import load_deferrals

    deferrals = load_deferrals(tmp_path)
    statuses = apply_deferrals(
        [DependencyStatus("pypi", "mcp", "1.30.0", "2.2.0", "pyproject.toml", True)],
        deferrals,
        date(2026, 9, 23),
    )
    assert statuses[0].deferred is True
    assert statuses[0].outdated is False
    assert "test" in statuses[0].note


def test_github_latest_tag_treats_timeout_as_fetch_failure():
    def timed_out(url: str) -> list[str]:
        raise subprocess.TimeoutExpired(["git", "ls-remote", "--tags", url], 1)

    assert _github_latest_tag("actions/checkout", timed_out) == ""


def test_docker_args_report_fetch_failed_on_timeout():
    def timed_out(url: str) -> list[str]:
        raise subprocess.TimeoutExpired(["git", "ls-remote", "--tags", url], 1)

    statuses = check_docker_args(ROOT, list_remote_tags=timed_out)
    uv_status = next(status for status in statuses if status.name == "UV_VERSION")
    assert uv_status.latest == "?"
    assert uv_status.note == "fetch failed"
    assert uv_status.outdated is False


def test_docker_args_release_source_uses_release_not_tag():
    def tags(url: str) -> list[str]:
        return ["v99.0.0"]

    def releases(url: str) -> str:
        return "https://github.com/jgraph/drawio-desktop/releases/tag/v31.7.0"

    statuses = check_docker_args(ROOT, list_remote_tags=tags, final_url=releases)
    drawio = next(status for status in statuses if status.name == "DRAWIO_DESKTOP_VERSION")
    assert drawio.latest == "v31.7.0"
    assert drawio.outdated is False


def test_docker_args_release_source_fetch_failed():
    def failed_url(url: str) -> str:
        raise OSError(url)

    def tags(url: str) -> list[str]:
        return ["0.12.21"]

    statuses = check_docker_args(ROOT, list_remote_tags=tags, final_url=failed_url)
    drawio = next(status for status in statuses if status.name == "DRAWIO_DESKTOP_VERSION")
    assert drawio.latest == "?"
    assert drawio.note == "fetch failed"
    assert drawio.outdated is False


def test_subprocess_timeout_is_bounded():
    assert SUBPROCESS_TIMEOUT_SECONDS >= HTTP_TIMEOUT_SECONDS > 0


def test_main_reports_timeout_as_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    def timed_out(repo_root: Path) -> list[DependencyStatus]:
        raise subprocess.TimeoutExpired(["uv", "lock"], SUBPROCESS_TIMEOUT_SECONDS)

    monkeypatch.setattr(check_dependency_updates_module, "check_dependency_updates", timed_out)
    assert main([]) == 1
    assert "dependency update check failed" in capsys.readouterr().err


def test_fetch_failures_are_unknown_and_counted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    def failed_json(url: str) -> object:
        raise OSError(url)

    def failed_tags(url: str) -> list[str]:
        raise OSError(url)

    monkeypatch.setattr(check_dependency_updates_module, "_default_fetch_json", failed_json)
    statuses = [
        *check_dependency_updates_module.check_pypi(ROOT, fetch_json=failed_json),
        *check_dependency_updates_module.check_uv_pin(ROOT, fetch_json=failed_json),
        *check_dependency_updates_module.check_github_actions(ROOT, list_remote_tags=failed_tags),
        *check_dependency_updates_module.check_docker_args(ROOT, list_remote_tags=failed_tags),
        *check_dependency_updates_module.check_docker_base(ROOT, fetch_json=failed_json),
    ]
    unknown = [status for status in statuses if status.fetch_failed]

    assert unknown
    assert all(not status.outdated for status in unknown)
    assert {
        "pypi",
        "uv-pin",
        "github-actions",
        "docker-arg",
        "docker-base",
    } <= {status.surface for status in unknown}

    def failed_report(_root: Path) -> list[DependencyStatus]:
        return unknown

    def no_deferrals(_root: Path) -> list[DependencyDeferral]:
        return []

    monkeypatch.setattr(check_dependency_updates_module, "check_dependency_updates", failed_report)
    monkeypatch.setattr(check_dependency_updates_module, "load_deferrals", no_deferrals)
    report_path = tmp_path / "report.json"
    assert main(["--repo-root", str(ROOT), "--json", str(report_path)]) == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["unknown_count"] == len(unknown)
    assert report["outdated_count"] == 0
    assert "| unknown |" in capsys.readouterr().out

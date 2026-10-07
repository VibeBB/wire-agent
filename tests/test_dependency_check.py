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
    check_python_versions,
    check_workflow_downloads,
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
    assert versions["openhands-sdk"] == "1.52.0"


def test_uv_pin_parsed():
    assert uv_version_pin(ROOT) == "==0.12.23"


def test_workflow_files_have_expected_suffixes():
    files = workflow_files(ROOT)
    assert all(f.suffix in {".yml", ".yaml"} for f in files)


def test_docker_arg_pins_parsed():
    args = docker_arg_pins(ROOT)
    assert args["UV_VERSION"] == "0.12.23"


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


def test_workflow_tool_pins_deduplicated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    def fetch_json(url: str) -> object:
        return {"info": {"version": "1.30.1"}}

    monkeypatch.setattr(
        check_dependency_updates_module,
        "_default_fetch_json",
        fetch_json,
    )
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "lint.yml").write_text(
        "      - run: uvx zizmor@1.30.1 .github/workflows\n"
        "      - run: uvx zizmor@1.30.1 .github/workflows\n",
        encoding="utf-8",
    )
    statuses = check_dependency_updates_module.check_github_actions(
        tmp_path, list_remote_tags=lambda url: []
    )
    zizmor = [s for s in statuses if s.surface == "pypi-uvx" and s.name == "zizmor"]
    assert len(zizmor) == 1
    assert zizmor[0].current == "1.30.1"
    assert zizmor[0].latest == "1.30.1"
    assert zizmor[0].outdated is False


def test_repo_workflows_cover_all_pinned_external_sources():
    actions = {
        status.name
        for status in check_dependency_updates_module.check_github_actions(
            ROOT, list_remote_tags=lambda url: ["v1.0.0"]
        )
    }
    downloads = {
        status.name
        for status in check_workflow_downloads(
            ROOT,
            fetch_json=lambda url: {"info": {"version": "1.30.1"}},
            list_remote_tags=lambda url: ["v1.0.0"],
        )
    }
    assert "github/codeql-action/upload-sarif" in actions
    assert {
        "rhysd/actionlint",
        "zizmor",
        "aquasecurity/trivy",
        "actionlint download checksum",
        "zizmor download checksum",
    } <= downloads


def test_subpath_action_pins_track_the_parent_repo(tmp_path: Path):
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "lint.yml").write_text(
        "steps:\n"
        "  - uses: github/codeql-action/upload-sarif@"
        "2892aa5e19bbd11bc0cff5427e3b750a04d9e3c2 # v4.38.2\n",
        encoding="utf-8",
    )
    seen: list[str] = []

    def remote_tags(url: str) -> list[str]:
        seen.append(url)
        return ["v4.38.2"]

    statuses = check_dependency_updates_module.check_github_actions(
        tmp_path, list_remote_tags=remote_tags
    )

    pin = next(status for status in statuses if status.name == "github/codeql-action/upload-sarif")
    assert pin.current == "v4.38.2"
    assert pin.latest == "v4.38.2"
    assert not pin.outdated
    assert seen == ["https://github.com/github/codeql-action"]


def test_workflow_download_pins_and_checksums(tmp_path: Path):
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "lint.yml").write_text(
        'tarball="actionlint_1.7.12_linux_amd64.tar.gz"\n'
        'curl "https://github.com/rhysd/actionlint/releases/download/v1.7.12/$tarball"\n'
        'echo "8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8'
        '  $RUNNER_TEMP/$tarball" | sha256sum -c -\n'
        'wheel="zizmor-1.30.1-py3-none-manylinux_2_28_x86_64.whl"\n'
        'echo "eee12266b793cb87ad4a7e3af2e72404f8a63e3de5eb099b80bf7b1cfd232a8e'
        '  $RUNNER_TEMP/$wheel" | sha256sum -c -\n'
        "      - uses: aquasecurity/trivy-action@ed142fd0673e97e23eac54620cfb913e5ce36c25\n"
        "        with:\n"
        "          version: v0.75.0\n",
        encoding="utf-8",
    )

    statuses = check_workflow_downloads(
        tmp_path,
        fetch_json=lambda url: {"info": {"version": "99.0.0"}},
        list_remote_tags=lambda url: ["v99.0.0"],
    )

    by_name = {status.name: status for status in statuses}
    assert by_name["rhysd/actionlint"].current == "v1.7.12"
    assert by_name["rhysd/actionlint"].outdated is True
    assert by_name["zizmor"].current == "1.30.1"
    assert by_name["zizmor"].latest == "99.0.0"
    assert by_name["aquasecurity/trivy"].current == "v0.75.0"
    assert by_name["aquasecurity/trivy"].outdated is True
    assert by_name["actionlint download checksum"].outdated is False
    assert by_name["zizmor download checksum"].outdated is False


def test_workflow_download_checksum_must_be_sha256(tmp_path: Path):
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "lint.yml").write_text(
        'tarball="actionlint_1.7.12_linux_amd64.tar.gz"\n'
        'echo "deadbeef  $RUNNER_TEMP/$tarball" | sha256sum -c -\n',
        encoding="utf-8",
    )

    statuses = check_workflow_downloads(
        tmp_path,
        fetch_json=lambda url: {"info": {"version": "1.0.0"}},
        list_remote_tags=lambda url: [],
    )

    checksum = next(status for status in statuses if status.name.endswith("checksum"))
    assert checksum.outdated is True
    assert checksum.latest == "invalid"


def test_workflow_downloads_cover_actionlint_and_trivy():
    def tags(url: str) -> list[str]:
        if "actionlint" in url:
            return ["v1.7.12"]
        if "trivy" in url:
            return ["v0.75.0"]
        return []

    statuses = check_dependency_updates_module.check_workflow_downloads(ROOT, list_remote_tags=tags)
    by_name = {status.name: status for status in statuses}
    actionlint = by_name["rhysd/actionlint"]
    assert actionlint.surface == "direct-download"
    assert actionlint.current == "v1.7.12"
    assert actionlint.latest == "v1.7.12"
    assert actionlint.outdated is False
    trivy = by_name["aquasecurity/trivy"]
    assert trivy.current == "v0.75.0"
    assert trivy.outdated is False

    outdated = check_dependency_updates_module.check_workflow_downloads(
        ROOT, list_remote_tags=lambda url: ["v9.9.9"]
    )
    tracked = {s.name: s for s in outdated}
    assert tracked["rhysd/actionlint"].outdated is True
    assert tracked["aquasecurity/trivy"].outdated is True


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
        return ["0.12.23"]

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
        *check_dependency_updates_module.check_workflow_downloads(
            ROOT, fetch_json=failed_json, list_remote_tags=failed_tags
        ),
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
        "direct-download",
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


def test_python_versions_skip_older_legs_when_source_covers_latest(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nrequires-python = ">=3.12"\n', encoding="utf-8"
    )
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(
        "jobs:\n  verify:\n    strategy:\n      matrix:\n"
        '        python-version: ["3.12", "3.13", "3.14", "3.15"]\n',
        encoding="utf-8",
    )
    statuses = check_python_versions(
        tmp_path, list_remote_tags=lambda url: ["v3.12.0", "v3.13.0", "v3.14.0", "v3.15.0"]
    )
    ci_statuses = [status for status in statuses if status.source.endswith("ci.yml")]
    assert ci_statuses
    assert all(not status.outdated for status in ci_statuses)


def test_python_versions_still_flag_source_without_latest(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nrequires-python = ">=3.12"\n', encoding="utf-8"
    )
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(
        "jobs:\n  verify:\n    steps:\n      - uses: actions/setup-python@x\n"
        '        with:\n          python-version: "3.12"\n',
        encoding="utf-8",
    )
    statuses = check_python_versions(
        tmp_path, list_remote_tags=lambda url: ["v3.12.0", "v3.13.0", "v3.14.0", "v3.15.0"]
    )
    ci_statuses = [status for status in statuses if status.source.endswith("ci.yml")]
    assert ci_statuses
    assert all(status.outdated for status in ci_statuses)

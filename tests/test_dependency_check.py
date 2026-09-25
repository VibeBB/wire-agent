from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from scripts.check_dependency_updates import (
    ROOT,
    DependencyStatus,
    apply_deferrals,
    dependency_names,
    docker_arg_pins,
    docker_base_image,
    lock_versions,
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
    assert versions["openhands-sdk"] == "1.49.6"


def test_uv_pin_parsed():
    assert uv_version_pin(ROOT) == "==0.12.19"


def test_workflow_files_have_expected_suffixes():
    files = workflow_files(ROOT)
    assert all(f.suffix in {".yml", ".yaml"} for f in files)


def test_docker_arg_pins_parsed():
    args = docker_arg_pins(ROOT)
    assert args["UV_VERSION"] == "0.12.19"


def test_docker_arg_matches_uv_pin():
    args = docker_arg_pins(ROOT)
    assert f"=={args['UV_VERSION']}" == uv_version_pin(ROOT)


def test_docker_base_image_parsed():
    base = docker_base_image(ROOT)
    assert base == ("debian", "13-slim")


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

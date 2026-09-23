from __future__ import annotations

from scripts.check_dependency_updates import (
    docker_arg_pins,
    docker_base_image,
    project_dependencies,
    uv_version_pin,
    workflow_files,
)


def test_project_dependencies_parsed() -> None:
    deps = dict(project_dependencies())
    assert "pydantic" in deps
    assert "mcp" in deps
    assert "openhands-sdk" in deps
    assert deps["openhands-sdk"] == "1.49.4"
    assert "pytest" in deps


def test_uv_pin_parsed() -> None:
    assert uv_version_pin() == "==0.12.18"


def test_workflow_files_have_expected_suffixes() -> None:
    files = workflow_files()
    assert all(f.suffix in {".yml", ".yaml"} for f in files)


def test_docker_arg_pins_parsed() -> None:
    args = docker_arg_pins()
    assert args["UV_VERSION"] == "0.12.18"


def test_docker_arg_matches_uv_pin() -> None:
    args = docker_arg_pins()
    assert f"=={args['UV_VERSION']}" == uv_version_pin()


def test_docker_base_image_parsed() -> None:
    base = docker_base_image()
    assert base == ("ubuntu", "26.04")

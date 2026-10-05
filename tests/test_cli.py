"""CLI surface tests (exit codes and advisory flags)."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from helpers import EXAMPLE_CONTRACT
from wire.cli import main, verdict_exit_code


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "wire", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"verdict": "pass"}, 0),
        ({"verdict": "ready"}, 0),
        ({"verdict": "fail"}, 1),
        ({"verdict": "blocked"}, 1),
        ({"verdict": "unknown"}, 1),
        ({}, 1),
    ],
)
def testverdict_exit_code_is_fail_closed(payload: dict[str, str], expected: int) -> None:
    assert verdict_exit_code(payload) == expected


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


def _fake_image(tmp_path: Path) -> Path:
    img = tmp_path / "harness-diagram.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    return img


def test_review_record_writes_validated_record(tmp_path: Path) -> None:
    img = _fake_image(tmp_path)
    findings = tmp_path / "findings.json"
    findings.write_text(
        json.dumps(
            [
                {
                    "category": "label_collision",
                    "severity": "warning",
                    "note": "W4 label touches C3 header",
                    "bbox": [0.4, 0.3, 0.1, 0.05],
                }
            ]
        ),
        encoding="utf-8",
    )
    result = _run(
        "review-record",
        "--image",
        str(img),
        "--model",
        "test-model",
        "--checklist",
        "harness_diagram",
        "--impression",
        (
            "The sheet is readable and the pin tables carry every wire end with "
            "gauge, color, and terminal data. The W4 label collides with the "
            "C3 header, which a fabricator would trip over, and a stray label "
            "crowds the right edge. Branch lengths anchor to mating faces so a "
            "no-context reader could still kit the parts."
            " A fabricator reading it on the shop floor would know where to start, "
            "which cavities are populated and which connector family to order. The "
            "remaining doubt is whether the splice note survives a monochrome "
            "print, so the next step is a grayscale render check."
        ),
        "--findings",
        str(findings),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    record_path = tmp_path / "review-visual-harness-diagram.advisory.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["tool"] == "vision_review"
    assert record["detail"]["image_sha256"] == hashlib.sha256(img.read_bytes()).hexdigest()
    assert record["detail"]["impression"].startswith("The sheet")
    assert record["detail"]["findings"][0]["category"] == "label_collision"


def test_review_record_rejects_bad_payload(tmp_path: Path) -> None:
    """A malformed finding can never produce a record (fail-closed)."""
    img = _fake_image(tmp_path)
    findings = tmp_path / "findings.json"
    findings.write_text(
        json.dumps([{"category": "not_a_category", "severity": "warning", "note": "x"}]),
        encoding="utf-8",
    )
    result = _run(
        "review-record",
        "--image",
        str(img),
        "--model",
        "test-model",
        "--checklist",
        "harness_diagram",
        "--impression",
        "x",
        "--findings",
        str(findings),
    )
    assert result.returncode != 0
    assert '"verdict": "fail"' in result.stdout
    assert not (tmp_path / "review-visual-harness-diagram.advisory.json").exists()


def test_review_record_requires_impression(tmp_path: Path) -> None:
    img = _fake_image(tmp_path)
    findings = tmp_path / "findings.json"
    findings.write_text("[]", encoding="utf-8")
    result = _run(
        "review-record",
        "--image",
        str(img),
        "--model",
        "test-model",
        "--checklist",
        "harness_diagram",
        "--findings",
        str(findings),
    )
    assert result.returncode != 0
    assert not (tmp_path / "review-visual-harness-diagram.advisory.json").exists()


def test_cli_import_writes_out(tmp_path: Path) -> None:
    out = tmp_path / "merged.contract.json"
    code = main(
        [
            "import",
            "--contract",
            str(EXAMPLE_CONTRACT),
            "--source",
            str(Path(__file__).parent / "fixtures" / "upstream" / "housing.envelope.json"),
            "--from",
            "mech-envelope",
            "--out",
            str(out),
        ]
    )
    assert code == 0
    merged = json.loads(out.read_text(encoding="utf-8"))
    assert merged["imported_sources"][0]["anchor_points"][0]["name"] == "clip-01"

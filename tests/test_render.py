"""Visual baseline tests — deterministic sha256 record/compare on renders."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from wire.render import RenderBaselineError, record_or_compare_baseline

_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c626001000000ffff03000006000557bfabd40000000049"
    "454e44ae426082"
)
_PNG2 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478d26360600001000005ff01a5f645400000000049454e44ae"
    "426082"
)


def _image(tmp_path: Path, name: str = "harness-diagram.png", data: bytes = _PNG) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def test_baseline_record_match_diff(tmp_path: Path) -> None:
    image = _image(tmp_path)
    baseline = tmp_path / "baseline.json"
    verdict, image_sha = record_or_compare_baseline(image, baseline)
    assert verdict == "recorded"
    assert baseline.is_file()
    record = json.loads(baseline.read_text(encoding="utf-8"))
    assert record["image_sha256"] == image_sha

    verdict, _ = record_or_compare_baseline(image, baseline)
    assert verdict == "match"

    image.write_bytes(_PNG2)
    verdict, _ = record_or_compare_baseline(image, baseline)
    assert verdict == "diff"


def test_baseline_missing_image_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(RenderBaselineError, match="image missing"):
        record_or_compare_baseline(tmp_path / "nope.png", tmp_path / "b.json")


def test_baseline_corrupt_fails_closed(tmp_path: Path) -> None:
    image = _image(tmp_path)
    baseline = tmp_path / "baseline.json"
    baseline.write_text("{not json", encoding="utf-8")
    with pytest.raises(RenderBaselineError, match="cannot read baseline"):
        record_or_compare_baseline(image, baseline)


def test_baseline_non_string_sha_fails_closed(tmp_path: Path) -> None:
    image = _image(tmp_path)
    baseline = tmp_path / "baseline.json"
    baseline.write_text('{"image_sha256": 42}', encoding="utf-8")
    with pytest.raises(RenderBaselineError, match="cannot read baseline"):
        record_or_compare_baseline(image, baseline)

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_publish_workflow_runs_when_its_file_changes() -> None:
    workflow = (ROOT / ".github/workflows/publish-wire-images.yml").read_text(encoding="utf-8")

    assert '      - ".github/workflows/publish-wire-images.yml"' in workflow
    assert '      - "scripts/update_image_digest_lock.py"' in workflow

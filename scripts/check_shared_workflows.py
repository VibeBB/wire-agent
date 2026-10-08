from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

EXPECTED: dict[str, str] = {
    ".github/workflows/pr-branch-cleanup.yml": (
        "fe82446007039eba98c595609e27f75cbc6067fe079a3912e3ec61dbece776ab"
    ),
    ".github/workflows/workflow-lint.yml": (
        "5e71f3cb72db9fc130f7f773c75340e8ba752045ece4ce5287076006651ce5b7"
    ),
    ".github/workflows/main-ci-failure-issue.yml#jobs": (
        "79ae82360a68c0db53d8663c0eb760c937f65db3f76c88bff858df0f0f03ec24"
    ),
    ".github/workflows/dependency-review.yml": (
        "77d3fcca14a2e62ca0931ce2d543f95a3e55109e2adc778801a7d4eff791fc35"
    ),
    ".github/workflows/scorecard.yml": (
        "3683625dac55f51bae0e034a5480db13c3c9e5de9e85a9d287d4a4ab4f407133"
    ),
    ".github/workflows/codeql.yml": (
        "3970c1d9d11b432486499e49bf26c26285a8a829b81532f896b2a4e7d030e7b6"
    ),
}
UNITS: dict[str, tuple[str, bytes | None]] = {
    ".github/workflows/pr-branch-cleanup.yml": (
        ".github/workflows/pr-branch-cleanup.yml",
        None,
    ),
    ".github/workflows/workflow-lint.yml": (
        ".github/workflows/workflow-lint.yml",
        None,
    ),
    ".github/workflows/main-ci-failure-issue.yml#jobs": (
        ".github/workflows/main-ci-failure-issue.yml",
        b"jobs:",
    ),
    ".github/workflows/dependency-review.yml": (
        ".github/workflows/dependency-review.yml",
        None,
    ),
    ".github/workflows/scorecard.yml": (
        ".github/workflows/scorecard.yml",
        None,
    ),
    ".github/workflows/codeql.yml": (
        ".github/workflows/codeql.yml",
        None,
    ),
}


def _read_unit(root: Path, path: str, marker: bytes | None) -> bytes:
    content = (root / path).read_bytes()
    if marker is None:
        return content
    offset = 0
    for line in content.splitlines(keepends=True):
        if line.rstrip(b"\r\n") == marker:
            return content[offset:]
        offset += len(line)
    raise ValueError("jobs: marker not found")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--print",
        action="store_true",
        help="print current SHA-256 hashes without checking EXPECTED",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    failures: list[str] = []
    for unit, (path, marker) in UNITS.items():
        try:
            content = _read_unit(root, path, marker)
        except (OSError, ValueError) as exc:
            actual = "missing"
            if args.print:
                print(f"{unit}: {actual}")
            else:
                failure = f"{path}: expected {EXPECTED[unit]}, got {actual} ({exc})"
                failures.append(failure)
            continue
        actual = hashlib.sha256(content).hexdigest()
        if args.print:
            print(f"{unit}: {actual}")
        elif actual != EXPECTED[unit]:
            failures.append(f"{path}: expected {EXPECTED[unit]}, got {actual}")
    if args.print:
        return 1 if failures else 0
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print("shared workflows match canonical hashes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

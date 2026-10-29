# Dependency updates

This document records the pinned versions in use, where they come from, and
the adoption decision for each. Update it in the same change that touches
`pyproject.toml`, a workflow pin, or a new external source.

## Runtime dependencies (pyproject.toml + uv.lock)

| Package | Pin | Source | Decision |
| --- | --- | --- | --- |
| pydantic | `>=2` | PyPI | Floor pin — v2 API only (`model_validate`, `model_dump`). |
| mcp | `>=1.29,<2` | PyPI | stdio server boundary; `<2` caps the breaking major. |

## SDK check group (plugin-load / install smoke only)

| Package | Pin | Source | Decision |
| --- | --- | --- | --- |
| openhands-sdk | `==1.55.1` | PyPI | Exact pin — plugin API contract; same pin as the sibling plugins so a merged conversation sees one SDK. |
| openhands-tools | `==1.55.1` | PyPI | Exact pin — matches SDK. |

The `sdk-check` group is installed by default (`tool.uv default-groups`) so
pyright strict can type `check_plugin_load.py`; the Docker image excludes it
via `uv export --no-dev`.

## Dev dependencies (dev group)

| Package | Pin | Notes |
| --- | --- | --- |
| packaging | `>=26` | Used by `scripts/check_dependency_updates.py` |
| pyright | `>=1.1.414` | strict mode |
| pytest | `>=9` | suite runner |
| pytest-xdist | `>=3` | `-n auto --dist loadgroup` |
| ruff | `>=0.16` | lint + format |

## Tooling pins

| Tool | Pin | Where |
| --- | --- | --- |
| uv | `==0.13.1` | `[tool.uv] required-version` |
| Python | `>=3.12`, CI matrix 3.12/3.13/3.14 (+3.15 canary leg) | pyproject `requires-python` |
| zizmor | `1.31.1` (sha256-verified wheel) | `workflow-lint.yml` |
| actionlint | `v1.7.12` (sha256-verified tarball) | `workflow-lint.yml` |
| trivy | `v0.76.0` (`version:` input) | `container-audit.yml`, `publish-wire-images.yml` |

## GitHub Actions pins

All `uses:` entries are pinned to a 40-char SHA with a `# vX.Y.Z` comment:

| Action | Pinned version |
| --- | --- |
| actions/checkout | v7.0.1 |
| astral-sh/setup-uv | v10.2.0 |
| actions/upload-artifact | v7.0.2 |
| github/codeql-action/upload-sarif | v4.38.2 |
| anchore/sbom-action | v0.24.3 |

## Docker image pins

| Item | Pin | Where |
| --- | --- | --- |
| debian base image | `13-slim` | `docker/wire-tools.Dockerfile` `FROM` |
| uv | `0.13.0` | `docker/wire-tools.Dockerfile` `ARG UV_VERSION` (must equal `[tool.uv] required-version`) |
| Python in image | `3.14` | `uv python install` inside the Dockerfile |

## Workflow git clone pins

| Item | Pin | Where |
| --- | --- | --- |
| CISOfy/lynis | `3.1.7` | `git clone --depth 1 --branch` in `container-audit.yml` |

The checker treats `git clone --branch <ref>` pins inside workflows as a
`git-clone` surface and compares the ref against the upstream repo's
highest semver tag, so a new Lynis release surfaces in the weekly report.

## Checked by `scripts/check_dependency_updates.py`

- PyPI dependencies (runtime + dev + sdk-check), resolved against latest
  PyPI release.
- uv required-version against PyPI `uv`.
- GitHub Actions `uses:` SHA pins against latest repo tag.
- `uvx` tool pins in workflows against PyPI.
- Dockerfile `ARG UV_VERSION` against the latest `astral-sh/uv` tag.
- Dockerfile `FROM debian:N-slim` against the newest Debian `N-slim` tag on
  Docker Hub (a `ubuntu:YY.MM` base is also understood and compared against
  the newest Ubuntu `YY.04` LTS tag).
- Workflow `git clone --branch` pins (e.g. CISOfy/lynis in
  `container-audit.yml`) against the upstream repo's latest semver tag.
- Direct-download tool pins in workflows: GitHub `releases/download` URLs
  (e.g. the actionlint tarball) and trivy `version:` inputs on
  aquasecurity actions, against the upstream repo's latest semver tag.
- Python minor pins: pyproject `requires-python`, Dockerfile
  `uv python install` / `uv venv --python` / `python3.X` pins,
  `.python-version`, and `python-version` pins in every workflow, against
  the latest stable CPython minor.

The weekly workflow posts the report to the "Dependency update check
report" issue. Deferred candidates are recorded in
`scripts/dependency_update_deferrals.json` with a re-check deadline.

## 2026-10-29 update (sdk 1.59.0, uv 0.13.6, drawio-desktop 32.6.1)

sdk `==1.55.1` -> `==1.59.0` (sdk + tools), uv `==0.13.1` -> `==0.13.6`,
pytest `9.1.1` -> `9.2.0`, ruff `0.17.x` -> `0.17.3` (lock), trivy
`v0.76.0` -> `v0.76.1`, codeql-action v4.39.0 -> v4.39.1, harden-runner
v2.22.1 -> v2.22.3, setup-uv v10.3.0 -> v10.3.3, docker/login-action
v4.6.0 -> v4.7.0. Full changelog review:
[SDK v1.59.0 feature evaluation](research/sdk-v1.59.0-feature-evaluation.md).
Deferrals unchanged (mcp 2.x, Python 3.15 default, Tauri 3.0.0-alpha where
applicable); the mcp deferral reason now cites SDK 1.59.0.

drawio-desktop `32.4.1` -> `32.6.1` (deb downloaded and sha256-verified).
Base image `debian:13-slim` digest re-pinned to the current tag digest.

## 2026-10-18 update (sdk 1.55.1, uv 0.13.1)

sdk `==1.54.0` -> `==1.55.1` (sdk + tools), uv `==0.13.0` -> `==0.13.1`,
zizmor `1.30.1` -> `1.31.1`, trivy `v0.75.0` -> `v0.76.0`, codeql-action
v4.38.3 -> v4.39.0. Full changelog review:
[SDK v1.55.1 feature evaluation](research/sdk-v1.55.1-feature-evaluation.md).
Deferrals unchanged (mcp 2.x, Python 3.15 default, Tauri 3.0.0-alpha where
applicable); reasons refreshed to cite SDK 1.55.1.

## Procedure

1. Run `uv run python scripts/check_dependency_updates.py` locally.
2. For each candidate, read the upstream release notes: record used APIs,
   defaults, breaking changes, and the adoption decision in this file.
3. Bump the pin in the same change (pyproject/uv.lock via `uv lock`,
   workflow SHA + comment, or `uvx` pin).
4. Run `verify_all.py --stage fast`.
5. If deferring: add `{name, reason, deadline}` to
   `scripts/dependency_update_deferrals.json`.

## Not covered

- Transitive dependencies (uv.lock is the record; bumps ride direct bumps).
- The wire-tools image digest lock (written only by the publish workflow,
  planned — see `docs/operations.md`).

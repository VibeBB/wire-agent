# Operations

## Verification stages

`scripts/verify_all.py` is the source of truth for verification stages;
enumerate with `--list`.

| Stage | Purpose |
| --- | --- |
| `docs` | markdown/link/ADR-index checks + `git diff --check` — doc-only changes |
| `fast` | `uv sync --locked`, ruff, format, pyright strict, pytest, docs — before every PR |
| `standard` | fast + plugin-load check + E2E authoring round-trip — contract or gate changes |

```bash
uv sync
uv run python scripts/verify_all.py --stage docs
uv run python scripts/verify_all.py --stage fast
uv run python scripts/verify_all.py --stage standard
```

pytest runs `-n auto --dist loadgroup` by default; `uv run pytest -n 0` for
single-test debugging. Parallel and sequential runs must produce identical
verdicts and artifact hashes.

## Dependency policy

PyPI dependencies are pinned in `pyproject.toml` and `uv.lock`. The
pinned OpenHands SDK version is `1.49.4` — the same pin as the sibling
plugins so a merged conversation sees one SDK. `--png` vision review
rasterizes the diagram through the unmodified `rsvg-convert` binary
(`librsvg2-bin`) plus `fonts-ipafont` for CJK coverage — both installed
in `docker/wire-tools.Dockerfile` and invoked as a subprocess, keeping
librsvg's LGPL out of the import set; without them the flag fails the
export step cleanly. When adding or removing a
dependency, update the checker targets in
`scripts/check_dependency_updates.py` and this document in the same change.
The weekly `check-dependency-updates` workflow reports candidates to a
"Dependency update check report" issue; deferrals are recorded with reason
and re-check deadline in `scripts/dependency_update_deferrals.json`.

## Releases

- Versions follow semver; `plugin.json`, `pyproject.toml`, and the skill
  version strings are bumped together by `scripts/bump_version.py`.
- `.github/workflows/release.yml` is `workflow_dispatch` only.
- Docker image digests live in `docker/image-digests.json` and are written
  only by the `publish-wire-images.yml` workflow; do not commit
  placeholder entries.
- `publish-wire-images.yml` builds and publishes `ghcr.io/<owner>/wire-tools`
  on `workflow_dispatch` and on pushes to main that touch `docker/**`,
  `.dockerignore`, `src/**`, `plugins/wire/**`, `examples/**`, or the
  project metadata (excluding the lock file and `docker/README.md`), then
  opens and merges the digest-lock pull request. Its checkout keeps
  `persist-credentials: true` because the job pushes the lock-update
  branch.
- `locked-image-check.yml` (weekly + post-publish dispatch) pulls the
  locked tools image and re-runs the authoring smoke check in the
  container.

## CI

- `ci.yml` runs on pushes to main, pull requests, merge groups,
  `workflow_call`, and `workflow_dispatch` (the publish workflow dispatches
  it on the lock-update branch): verify (Python 3.12/3.13), plugin-load
  against the pinned SDK, and a container smoke check when the tools image
  changes.
- `workflow-lint.yml` runs zizmor on every pull request, merge group,
  main pushes touching `.github/**`, and weekly; SARIF uploads to code
  scanning. Every `uses:` entry is pinned to a 40-character SHA with a
  `# vX.Y.Z` comment; checkout uses `persist-credentials: false` except in
  the image publish job (the lock-update PR needs push credentials); every
  job sets `timeout-minutes`.
- `dependabot.yml` monitors GitHub Actions and uv weekly (uv with a
  seven-day cooldown).

## Git

English commit messages. No `git add .`, no amend, no `--no-verify`, no
force push, no direct pushes to main, no destructive reset/clean/checkout.
Do not commit generated `out/` artifacts, secrets, or environment files.
Split dependent changes into bottom-up stacked PRs.

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
pinned OpenHands SDK version is `1.49.5` — the same pin as the sibling
plugins so a merged conversation sees one SDK. Diagram rendering and
all raster/PDF/SVG/HTML exports run the unmodified `drawio-desktop`
binary (`draw.io`) under `xvfb-run`, plus `fonts-ipafont` for CJK
coverage — installed in `docker/wire-tools.Dockerfile` from the
pinned, sha256-verified upstream `.deb` (`DRAWIO_DESKTOP_VERSION` /
`DRAWIO_DESKTOP_SHA256` ARGs) and invoked as a subprocess behind an
adapter, keeping Electron's code out of the import set; without it the
export fails closed — a missing drawio produces no partial diagram
artifact. When adding or removing a
dependency, update the checker targets in
`scripts/check_dependency_updates.py` and this document in the same change.
The weekly `check-dependency-updates` workflow reports candidates to a
"Dependency update check report" issue; deferrals are recorded with reason
and re-check deadline in `scripts/dependency_update_deferrals.json`.

## Vision support

Diagram review and photo intake are L2 aids. When the conversation model
is vision-capable, `FileEditorTool` sends raster renders
(`harness-diagram.png/.jpg`, pinout photos, manufactured-product photos)
to it directly. When it is not, wire-review and wire-brief declare the
builtin `inspect_image_with_vision` tool, which consults a saved
vision-capable LLM profile (`LLMProfileStore`, e.g. saved via
`store.save("vision", LLM(model="..."))` or the canvas settings UI). If
no vision-capable profile exists the agents skip vision rather than
guess — no degradation of gate authority either way.

`wire_drawio` / `python -m wire drawio` proxy the full `drawio -x`
surface; see `plugins/wire/commands/export.md` for the flag cheat sheet
(layer selection, `--size page` print PDFs, `-u` uncompressed XML,
`--theme`, `--layout`).

## Intake attachments and evidence binding

User-attached images are materialized to `<workspace>/intake/attachments/`
by the `intake-attachments` hook (session_start, user_prompt_submit, stop;
ADR-0005). The hook scans the agent-canvas event store
`~/.openhands/agent-canvas/dev_conversations/<session_id>/events/` —
override with `$WIRE_AGENT_EVENTS_DIR` — decodes each `data:` image to
`<sha256[:12]>.<ext>`, and appends provenance to `manifest.jsonl`; the
output dir is overridable via `$WIRE_INTAKE_ATTACHMENTS_DIR`. When the
events directory is unreachable (remote runtimes) the hook exits quietly
and the fallback is dropping files into `intake/` manually. `Assumption`
and `OpenQuestion` records may bind such a file with an `evidence` field
(`kind`, `path`, `sha256`, `note`); `check_intake` verifies existence and
hash — fail-closed, same as the `contract_sha256` binding.

## OpenHands runtime surfaces

Runtime policy surfaces that the plugin declares but the host executes:

- `permission_mode: never_confirm` on every wire sub-agent. The SDK's
  task path (`openhands-tools` `task/manager.py`, verified 1.49.5 and
  upstream `main`) never attaches a `security_analyzer` to the child
  `LocalConversation`, so `confirm_risky` saw every action as `UNKNOWN`
  and auto-resumed — zero gating plus status churn. `never_confirm`
  declares the real behavior; revisit if the SDK propagates the parent's
  analyzer.
- `model:` resolves through `LLMProfileStore` (`~/.openhands/profiles/`).
  Authoring sub-agents (wire-brief, wire-design) use `vibebb-author`;
  wire-review uses `vibebb-review`. A missing profile raises `ValueError`
  at task spawn — create the profiles (canvas LLM settings or
  `LLMProfileStore.save`) before invoking the agents. To fall back to the
  conversation model, set `model: inherit` locally.
- Secrets: `${VAR}` / `${VAR:-default}` in `mcp_config` expands through
  the conversation `SecretRegistry` before env, and `wire_launcher.py`
  forwards `OPENHANDS_*`/`WIRE_*` env into the tools container — a
  canvas-registered `WIRE_*` secret reaches `wire_*` tool code
  end-to-end. Bash commands also receive registry values when the key
  name appears in the command text.
- The `safety-rail` `pre_tool_use` hook (`hooks/scripts/safety_rail.py`)
  denies a deterministic denylist on terminal commands: root/home `rm
  -rf`, block-device writes, power commands, and the git operations the
  working agreement bans. It is advisory depth — not a security
  analyzer — and passes everything it does not positively recognize.
- `.openhands/memory/MEMORY.md` seeds the project-tier persistent
  memory loaded when the host enables `AgentContext(load_memory)`
  (canvas "Settings > Agent Context"). The agent maintains the index;
  keep the seed to durable facts only.
- `StuckDetector` is on by default for every conversation including
  task sub-agents; `max_iteration_per_run` remains the repo-side bound.

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
- `dependabot.yml` monitors GitHub Actions weekly. The uv ecosystem is
  intentionally excluded (Dependabot's bundled uv cannot satisfy
  `[tool.uv] required-version`), so Python dependency updates stay covered
  by the weekly check-dependency-updates.yml report.

## Git

English commit messages. No `git add .`, no amend, no `--no-verify`, no
force push, no direct pushes to main, no destructive reset/clean/checkout.
Do not commit generated `out/` artifacts, secrets, or environment files.
Split dependent changes into bottom-up stacked PRs.

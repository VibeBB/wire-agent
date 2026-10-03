# Operations

## SBOM attestations

`publish-wire-images.yml` generates and attests a package-level SPDX-2.3 SBOM
for the published tools digest and uploads the full Syft SBOM as a 90-day
workflow-run artifact. The returned attestation URL is stored as
`sbom_attestation`; `locked-image-check.yml` verifies it when present and
warns while continuing when it is absent.
The attested SBOM omits file entries and relationships involving files to
stay below the 16 MiB limit.

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
pinned OpenHands SDK version is `1.50.1` — the same pin as the sibling
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
and re-check deadline in `scripts/dependency_update_deferrals.json`. Fetch
failures are reported as unknown and keep the issue open until they resolve.

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
  at task spawn, so the `session_start` hook
  `hooks/scripts/ensure_llm_profiles.py` clones the conversation's
  `active_profile` into `vibebb-author.json`/`vibebb-review.json` when
  they are absent — edit those files afterwards to route the authoring
  or review lane at a different model. To fall back to the conversation
  model, set `model: inherit` locally.
- Secrets: `${VAR}` / `${VAR:-default}` in `mcp_config` expands through
  the conversation `SecretRegistry` before env, and `wire_launcher.py`
  forwards `OPENHANDS_*`/`WIRE_*` env into the tools container — a
  canvas-registered `WIRE_*` secret reaches `wire_*` tool code
  end-to-end. Bash commands also receive registry values when the key
  name appears in the command text.
- The tools container runs as the host uid, whose home does not exist
  inside the image: the launcher pins `HOME`/`TMPDIR`/`XDG_*` to `/tmp`
  instead of forwarding the host values so fontconfig, ezdxf and other
  cache-writing tools work. Source/image resolution still consults both
  `$HOME` and the account's real home for the OpenHands extension cache,
  so a `HOME` override applied to the container does not blind the
  launcher to `~/.openhands/cache/extensions/wire-agent-*`.
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
  placeholder entries. The same entry ships inside the plugin at
  `plugins/wire/skills/wire-workflow/tools-image.json` (rewritten by the
  same workflow) so an installed plugin resolves the pinned tools image
  without the extension cache — `wire_launcher.py` checks
  `<plugin>/tools-image.json`, then `<plugin>/skills/*/tools-image.json`,
  then `docker/image-digests.json`.
- `publish-wire-images.yml` builds and publishes `ghcr.io/<owner>/wire-tools`
  on `workflow_dispatch` and on pushes to main that touch `docker/**`,
  `.dockerignore`, `src/**`, `plugins/wire/**`, `examples/**`, or the
  project metadata, the publisher workflow, or the lock-update script
  (excluding `docker/image-digests.json`, the plugin pin, and
  `docker/README.md`), then opens and merges the digest-lock pull request.
  It attests the published image and records the attestation URL in both
  lock entries (ADR-0008). Its checkout keeps `persist-credentials: true`
  because the job pushes the lock-update branch.
- `locked-image-check.yml` (main pushes, weekly, and post-publish dispatch)
  validates the image lock, prewarms the pinned tools image through
  `wire_launcher.py`, runs `doctor` and the shipped authoring example, and
  verifies available provenance and SBOM attestations. Existing pins without
  attestation metadata warn and continue. Emitted design reports are uploaded
  as a run artifact, including on smoke failure.

## CI

- `ci.yml` runs on pushes to main, pull requests, merge groups,
  `workflow_call`, and `workflow_dispatch`; the publisher dispatches both
  `ci.yml` and `workflow-lint.yml` on the lock-update branch. Jobs are verify
  (Python 3.12/3.13), plugin-load
  against the pinned SDK, and a container smoke check when the tools image
  changes.
- `workflow-lint.yml` runs actionlint 1.7.12 and zizmor on every pull
  request, dispatched run, main push touching `.github/**`, and weekly;
  SARIF uploads to code scanning. `.github/actionlint.yaml` declares the
  `ubuntu-26.04` runner label so other unknown labels remain lint errors.
  Every `uses:` entry is pinned to a 40-character SHA with a `# vX.Y.Z`
  comment; checkout uses `persist-credentials: false` except in the image
  publish job (the lock-update PR needs push credentials); every job sets
  `timeout-minutes`.
- `dependabot.yml` monitors GitHub Actions and Docker dependencies weekly,
  with seven-day cooldowns and GitHub Actions updates grouped together. The
  uv ecosystem is intentionally excluded (Dependabot's bundled uv cannot
  satisfy `[tool.uv] required-version`), so Python dependency updates stay
  covered by the weekly check-dependency-updates.yml report.

## Git

English commit messages. No `git add .`, no amend, no `--no-verify`, no
force push, no direct pushes to main, no destructive reset/clean/checkout.
Do not commit generated `out/` artifacts, secrets, or environment files.
Split dependent changes into bottom-up stacked PRs.

## Launcher-side verification

`WIRE_VERIFY_ATTESTATION` accepts `auto` (the default), `require`, or `off`.
Before pulling a lock-provided image, and on every `prewarm`, the launcher
uses `gh attestation verify` with the lock entry and publisher workflow.
`auto` prints one note and skips for an image override, missing attestation,
missing `gh`, or failed `gh auth status`; once verification starts, failure
or timeout prevents the pull. `require` makes skip conditions errors, while
`off` never verifies. Ordinary invocations do not re-verify a locally
present image, and `--warn` doctor paths never verify.

## Container hardening

Three layers were adopted after a comparative evaluation of Lynis,
`docker build --check`, Trivy, Grype, Dockle, and hadolint:

- **Dockerfile lint** (`dockerfile-lint` job in `ci.yml`): hadolint
  v2.15.1 via `hadolint-action` v3.5.0 plus `docker build --check`
  (BuildKit built-in). `.hadolint.yaml` allows only docker.io and
  ghcr.io registries and waives DL3008 (exact deb pins rot when archives
  drop them; downloaded tools are already version+sha256 pinned) and
  DL3066 (the `wire` account is intentionally named, uid 1000).
- **Image scan on publish** (`publish-wire-images.yml`): Trivy v0.75.0
  via `trivy-action` v0.36.0 scans the pushed digest for
  CRITICAL/HIGH fixable vulnerabilities, secrets, and misconfiguration,
  gated (`exit-code 1`), with SARIF uploaded to code scanning
  (`category: trivy-wire-tools`) and a full JSON report as an artifact.
  The action is SHA-pinned and `version:` is explicit — the March 2026
  Trivy supply-chain compromise made both non-negotiable.
- **Weekly audit** (`container-audit.yml`, Mondays 03:17 UTC): pulls the
  pinned digest from `docker/image-digests.json`, re-scans with a fresh
  vulnerability DB (new CVEs against the frozen image), runs the Docker
  CIS compliance report, runs an informational in-image Lynis 3.1.7
  audit, aggregates `container-hardening.json` (artifact), and
  edits/creates a "Container hardening report" issue. The issue closes
  automatically when fixable HIGH/CRITICAL findings reach zero. The
  Lynis Hardening Index is recorded as a trend metric only — its
  denominator shifts with container-skipped tests, so it never gates.

Not adopted, with reasons: `lynis audit dockerfile` (~6 greps, frozen
since 2018, subset of hadolint, hardening index always 1);
Dockle (v0.4.15 stale; its CIS-derived checks are covered by Trivy's
`--compliance docker-cis` report); Grype (equivalent for the SBOM path,
kept as fallback); checkov (redundant third linter); `cisofy/lynis`
Docker image (does not exist — Lynis runs from a pinned git clone);
non-root USER enforcement and HEALTHCHECK enforcement (CI tools images —
deferred policy decisions).

Changelog evaluation for the adopted pins is in the introducing PR.
Suppressions: `.hadolint.yaml` waivers above; `.trivyignore` holds
time-boxed finding IDs — entries must carry an `exp:` date and a
rationale line here when added.

The uv-managed CPython's bundled `pip` payload (vendored urllib3,
msgpack, setuptools — never invoked; dependencies install via `uv` and
the shipped venv is pip-less) is stripped in the `uv python install`
layer, so the publish gate stays clean without `.trivyignore` waivers.

The weekly audit runs Lynis as container root (`--user 0`) with the
committed `docker/lynis-container.prf` profile, which skips tests that
are inapplicable inside a container (kernel/systemd/mounts/storage/
network/PAM/accounting are governed by the runtime flags below, not the
image fs). The profile raises the Hardening Index from ~58 to ~70 and
reduces the suggestion list to image-actionable items; remaining
suggestions are fixed in the Dockerfile (`UMASK 027` in login.defs) or
silenced only with a documented reason.

`wire_launcher.py` applies the runtime-hardening flags the container
profile defers to: `--network none`, `--user uid:gid`,
`--cap-drop ALL`, `--security-opt no-new-privileges`. A `--read-only`
root filesystem stays an optional hardening for callers that supply
tmpfs for tools that need scratch space.

## CI runner network auditing

CI and image-publishing jobs use `step-security/harden-runner` in audit-only mode. It observes network egress without blocking requests; per-run insights are available in the GitHub Actions job summary.

## Digest-lock PR verification

The publisher dispatches `ci.yml` and `workflow-lint.yml` on the lock branch, then polls the authoritative required-check set for up to 30 minutes. Non-required failures do not block publishing; a concluded required-check failure or a PR closed without merge fails the job. A PR merged externally triggers the existing post-merge main workflows without waiting for their results. If required checks remain pending at the deadline, the publisher arms squash auto-merge with branch deletion and exits successfully so branch protection can complete the merge.

SPDX generation prefers the GHCR registry source, writes temporary data under
the runner's temporary directory, and disables file metadata. The publisher
removes file entries and relationships involving files to produce the
package-level SPDX-2.3 SBOM. A guard reports disk space and the attested SBOM
size after transformation and fails above 16 MiB; the full Syft SBOM is
uploaded as a 90-day workflow-run artifact.

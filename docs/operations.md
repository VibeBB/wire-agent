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

### Partial runs

`--list` dumps each stage's commands as JSON. Run only the slice you touched
instead of a full stage — the groups are `lint`, `unit`, and `docker`
(standard/drawio stages):

```bash
uv run python scripts/verify_all.py --stage fast --group lint
uv run python scripts/verify_all.py --stage fast --match test_gates
uv run python scripts/verify_all.py --stage standard --group docker
```

CI uses the same flags for its matrix legs, so a local partial run reproduces
a failing check exactly. Run the full `fast` stage before submitting.

## Dependency policy

PyPI dependencies are pinned in `pyproject.toml` and `uv.lock`. The
pinned OpenHands SDK version is `1.52.0` — the same pin as the sibling
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
The checker covers: PyPI direct/dev pins against `uv.lock`, lock-file
transitive drift, the uv required-version, GitHub Actions `uses:` SHA pins
(including subpath actions such as `github/codeql-action/upload-sarif`,
which share the parent repo's tags), `uvx` tool pins, direct-download pins
inside workflows (the actionlint release tarball version + sha256, the
sha256-verified zizmor wheel, and `version:` inputs on aquasecurity
actions), Dockerfile ARG pins, the Docker base image tag, in-workflow
`git clone --branch` pins, and the CPython minor line.

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
- `.github/workflows/release.yml` is `workflow_dispatch` only. Its
  `dry_run` input rehearses a release without writing anything: the
  bump job computes the would-be version with
  `bump_version.py --dry-run`, checks the tag is free, emits HEAD as the
  release SHA, and the downstream verify/install-smoke/build jobs still
  run against it while tag and release creation are skipped. The
  bump-version state machine — version resolution, tag check, direct
  push, and the self-approving + dispatched-checks + auto-merge
  fallback PR — lives in `scripts/release_bump.sh` (the workflow step
  is a thin wrapper) and is covered by `tests/test_release_bump.py`
  (stubbed `gh`, local git remotes).
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
  because the job pushes the lock-update branch. It accepts a `dry_run`
  dispatch input that rehearses the publish: the tools image builds into
  the local daemon and the Trivy gates, SBOM chain, measurements, and
  smoke checks still run against it, but nothing is pushed, promoted
  (`:latest`), attested, locked, or dispatched, and no SARIF reaches
  code scanning. The run summary lists every skipped step.
- `locked-image-check.yml` (main pushes, weekly, and post-publish dispatch)
  validates the image lock, prewarms the pinned tools image through
  `wire_launcher.py`, runs `doctor` and the shipped authoring example, and
  verifies available provenance and SBOM attestations. Existing pins without
  attestation metadata warn and continue. Emitted design reports are uploaded
  as a run artifact, including on smoke failure.

## CI

- `ci.yml` runs on pushes to main, pull requests, merge groups,
  `workflow_call`, and `workflow_dispatch`; see "Digest-lock PR
  verification" for how the publisher triggers checks on the lock-update
  branch. Jobs are verify
  (Python 3.12/3.13), plugin-load
  against the pinned SDK, and a container smoke check when the tools image
  changes. The e2e and dockerfile-lint jobs are gated on the `changes`
  job's code-scope output, so docs-only pull requests skip them.
- `workflow-lint.yml` runs actionlint 1.7.12 and zizmor on every pull
  request, dispatched run, main push touching `.github/**`, and weekly;
  SARIF uploads to code scanning. zizmor runs from a sha256-verified
  wheel download (not an unpinned `uvx` fetch), with `GH_TOKEN` online
  audits except on `bot/update-image-digests-*` branches where it runs
  `--offline` because the branch may be deleted mid-run. A separate gate
  step fails the job on any SARIF result. `.github/actionlint.yaml` declares the
  `ubuntu-26.04` runner label so other unknown labels remain lint errors.
  Every `uses:` entry is pinned to a 40-character SHA with a `# vX.Y.Z`
  comment; checkout uses `persist-credentials: false` except in the image
  publish job (the lock-update PR needs push credentials); every job sets
  `timeout-minutes`.
- `dependency-review.yml` (shared) requires the repository's Dependency
  graph setting to be enabled (Settings → Advanced Security); the job
  fails with "Dependency review is not supported on this repository"
  otherwise — a one-time repo-settings prerequisite the workflow cannot
  self-check.
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
- **Image scan on publish** (`publish-wire-images.yml`): the build
  pushes only the immutable `<sha>-tools` tag. Trivy v0.75.0
  via `trivy-action` v0.36.0 then scans the pushed digest for
  CRITICAL/HIGH fixable vulnerabilities, secrets, and misconfiguration —
  a full JSON report first (always produced, even when the gate fails),
  then the gated SARIF scan (`exit-code 1`) uploaded to code scanning
  (`category: trivy-wire-tools`). Only after every gate passes does the
  `Promote :latest` step retag the digest to `:latest` via
  `docker buildx imagetools create`, so a failing image never serves
  `:latest`. The action is SHA-pinned and `version:` is explicit — the
  March 2026 Trivy supply-chain compromise made both non-negotiable.
- **Weekly audit** (`container-audit.yml`, Mondays 03:17 UTC): pulls the
  pinned digest from `docker/image-digests.json`, re-scans with a fresh
  vulnerability DB (new CVEs against the frozen image), runs the Docker
  CIS compliance report, runs an informational in-image Lynis 3.1.7
  audit (cloned at tag `3.1.7` then checked out detached at the pinned
  commit `2e99f92265760b73fd6b139868eb8d4116624030`), aggregates
  `container-hardening.json` (artifact), and maintains a persistent
  "Container hardening report" issue edited in place (`--state all`
  lookup so the newest open *or* closed issue is reused). A new issue
  is created only when the gate has fixable HIGH/CRITICAL findings to
  track; an open issue closes when the gate reaches zero and a closed
  one reopens if they return — a green run with no existing issue
  writes nothing, so it never does the create+close dance. A
  `workflow_dispatch` `dry_run` input runs every scan and the report
  while skipping the issue write. The report tracks the unfixed
  CRITICAL/HIGH counts so the accepted exposure is visible between
  weekly runs. The Lynis Hardening Index is recorded as a trend metric
  only — its denominator shifts with container-skipped tests, so it
  never gates. The CIS aggregator (`scripts/container_hardening_report.py`)
  walks `Results` recursively for `MisconfSummary` nodes and fails the
  step when zero checks were evaluated, so dead telemetry cannot
  masquerade as coverage; the scan itself retries once keyed on that
  payload check rather than the exit code. All scans share a weekly
  `actions/cache` Trivy DB keyed `cache-trivy-<ISO year>-W<week>`
  (`TRIVY_CACHE_DIR` under `$RUNNER_TEMP`); this job owns the save and
  `publish-wire-images.yml` restores the same key read-only. The full
  scan skips vendored `boto3`/`googleapiclient` data files that produced
  ~620 zero-failure misconfig targets.

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
silenced only with a documented reason. Because the tightened umask
makes Lynis write its report and log 0640 root-owned, the audit step
`chmod 644`s both files so the runner-side grep can read the index.

`wire_launcher.py` applies the runtime-hardening flags the container
profile defers to: `--network none`, `--user uid:gid`,
`--cap-drop ALL`, `--security-opt no-new-privileges`. A `--read-only`
root filesystem stays an optional hardening for callers that supply
tmpfs for tools that need scratch space.

### CIS baseline

The Trivy CIS compliance scan reports `DS-0002` (image runs as root) and
`DS-0026` (no `HEALTHCHECK`) on every tools image. Both are waived with
`exp:` entries in `.trivyignore`: these are CI build/tool containers, not
deployed services — workflows that need a non-root UID already run the
image with `docker run --user`, and batch tooling has no health endpoint
to probe. The waivers renew or get re-fixed by Dockerfile changes when
they lapse.

## CI runner network auditing

Every job in the repo-specific workflows starts with
`step-security/harden-runner` in audit-only mode (the five shared
workflows stay byte-identical to the family canon and are not modified
locally). It observes network egress without blocking requests; per-run
insights are available in the GitHub Actions job summary.

## Digest-lock PR verification

The publisher polls the authoritative required-check set for up to 15 minutes. Non-required failures do not block publishing; a concluded required-check failure or a PR closed without merge fails the job. A PR merged externally triggers the existing post-merge main workflows without waiting for their results. If required checks remain pending at the deadline, the publisher arms squash auto-merge with branch deletion and exits successfully so branch protection can complete the merge.

Check triggers on the lock branch are pull_request-primary: token-created
`bot/update-image-digests-*` pull requests do fire `pull_request` runs
in this repository, so the publisher polls `gh run list --event
pull_request` for ~3 minutes (`PUBLISH_PIN_PR_RUN_WAIT_ATTEMPTS` ×
`PUBLISH_PIN_PR_RUN_WAIT_SECONDS`) and then re-checks, per workflow,
whether a pull_request run already covers the pin PR's head SHA before
falling back to explicit `workflow_dispatch` of `ci.yml` and
`workflow-lint.yml` — a dispatch of a run already covering the head is a
duplicate and is skipped. On a dispatch `422 No ref found` the script
re-checks the PR state: `MERGED`/`CLOSED` means the create→dispatch race
resolved itself and is tolerated. After a successful merge the publisher
(and the 6-hourly `digest-lock-sweep.yml` — which also backfills merges
that landed via armed auto-merge after the publisher exited, since a
token merge does not fire push workflows) dispatches `ci.yml`,
`locked-image-check.yml`, and `workflow-lint.yml` on main for post-merge
verification. `locked-image-check.yml` additionally runs on pull requests
that touch `docker/image-digests.json` or the plugin tools pin, so its
schema validation, attestation verification, image pull, smoke, and the
`:latest`-vs-locked-digest drift assertion all gate the pin PR itself.

SPDX generation prefers the GHCR registry source, writes temporary data under
the runner's temporary directory, and disables file metadata. The publisher
removes file entries and relationships involving files to produce the
package-level SPDX-2.3 SBOM. A guard reports disk space and the attested SBOM
size after transformation and fails above 16 MiB; the full Syft SBOM is
uploaded as a 90-day workflow-run artifact.

## Settings-level posture (recorded decisions)

The following live in repository Settings rather than code; they are
intentional for the solo-maintainer bot-merge workflow and are recorded
here so audits do not re-flag them:

- Branch protection does not require approving reviews, code owners, or
  "apply to administrators": every merge is performed by automation
  (digest-lock, version-bump, and Devin PRs), so required approvers would
  only add friction to a pipeline that already gates on the required-check
  set. OpenSSF Scorecard reports this as Branch-Protection 3 and
  Code-Review 0; that is the recorded trade-off, not an oversight.
- The Dependency graph must stay enabled for `dependency-review.yml` to
  evaluate pull requests.
- `release.yml` is dispatch-only; run it once with `dry_run=true` before
  the first real release to rehearse bump, verify, and install-smoke
  without creating a GitHub release.

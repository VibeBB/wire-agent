# Agent Working Agreement

> Target: OpenHands Software Agent SDK v1.49.4, Python 3.12+

This document is the working agreement for implementation, verification, and
documentation in this repository. The README is the product overview,
`docs/` holds the specifications and operational policy, `docs/adr/` holds
the design decisions, and the Pydantic models in `src/wire/contract.py` and
`src/wire/intake.py` are the contract source of truth.

README, docs, issues, PRs, code comments, identifiers, and commit messages
are written in English. The README keeps a Japanese section at the end.

## Layout

```text
src/wire/                 # deterministic wire-harness core
├── contract.py           # HarnessContract schema (the truth source)
├── intake.py             # intake/provenance schema + coverage check
├── standards.py          # wire specs, derating, bend factors, connector families
├── gates.py              # authoritative gate runner
├── export.py             # wire list/cut table/BOM/diagram + manifest/provenance
├── report.py             # design-report.json/md
├── doctor.py             # environment probe
├── imports.py            # connectivity/envelope import adapters
├── cli.py                # python -m wire {doctor,intake,author,gates,export,import}
└── mcp_server.py         # stdio MCP boundary
plugins/wire/             # OpenHands plugin
├── skills/               # wire-workflow, wire-contract, wire-gates,
│                         # wire-connectivity
├── agents/               # wire-brief, wire-design, wire-review
├── commands/             # /wire:design, /wire:doctor, /wire:gates, /wire:export
├── hooks/                # session_start doctor, pre_tool_use artifact guard,
│                         # stop status report
├── scripts/wire_launcher.py
├── .mcp.json
└── .plugin/plugin.json
tests/
scripts/
docker/                   # wire-tools.Dockerfile + image digest lock
examples/                 # contract JSON used by docs and tests
docs/adr/  docs/research/
```

## Invariants

- The harness contract and intake files are the source of truth; generated
  artifacts (wire lists, cut tables, BOMs, drawio/SVG diagrams, manifest,
  provenance, design report, KBL/VEC exports) are projections and are never
  edited by hand — the `protect-generated` hook blocks such writes.
- Pass/fail verdicts are produced only by the deterministic gates in
  `src/wire/gates.py` and the schemas they serialize.
- LLM output, conversation text, review comments, and vision observations
  are L2 steering aids and are never promoted to a verdict; they may only
  push toward stopping, never toward passing.
- Missing tools, parse failures, unexecuted gates, and unknown states are
  fail-closed: a gate that did not run or could not measure reports
  `unknown`, which fails the design verdict.
- Do not relax thresholds, expected values, or gate rules to achieve a pass.
- Always specify `encoding="utf-8"` when reading or writing artifacts and
  reports as text.
- Never import-bind GPL/AGPL/LGPL code. Copyleft tools may only ever run as
  unmodified subprocesses behind an adapter.
- Never write API keys, tokens, or secrets to logs, inputs, or commits.
- Provide negative tests that deliberately corrupt the judged input and
  confirm the corrupted input fails (see `tests/test_gates.py`).
- wire-agent interoperates with mechanical-agent, electrical-circuit-agent,
  and bard-agent through workspace JSON contracts and `task` delegation
  only (ADR-0003). It has no acd-agent dependency: no imports, no Design
  Graph links, no schema reuse.

## Plugin boundary

- Do not build custom tool, event, history, task, or executor
  infrastructure; delegate to the OpenHands SDK.
- Invoke sub-agents only with `task` (`TaskToolSet`); wire agents declare
  their required hooks per AgentDefinition because plugin hooks do not
  propagate to sub-agents.
- AgentDefinitions do not declare `skills:`; SKILL.md paths are referenced
  from prompts.
- The `wire` MCP server exposes only deterministic entry points (the same
  functions `python -m wire` uses). It contains no agent logic.
- `plugins/wire/scripts/wire_launcher.py` is the single exec point for
  hooks and the MCP server: it runs `python -m wire` inside the pinned
  `wire-tools` image. Any argument other than `mcp_server`/`prewarm` is
  forwarded to `wire.cli`, so docs write `python3 <launcher> <args>`.
- Skills use `triggers:` (`KeywordTrigger`).

## Parallel execution

- Accept parallelism through explicit `--jobs`-style arguments; default
  `min(os.cpu_count() or 1, N)`.
- `ThreadPoolExecutor` for I/O and subprocess waits.
- The parallelism degree must not change artifacts, hashes, or verdicts.
  Pin sequential == parallel with a regression test when a parallel path is
  added.

## Dependencies

PyPI dependencies are pinned in `pyproject.toml` and `uv.lock`. When adding,
removing, or moving a dependency, adding a version ARG or FROM image to
`docker/wire-tools.Dockerfile`, or starting to use a new external source
(other than PyPI), update in the same change: the checker logic in
`scripts/check_dependency_updates.py` (and its tests) plus
`docs/operations.md`, and run `uv run python
scripts/check_dependency_updates.py` locally. For deferred candidates,
record the reason and a re-check deadline in
`scripts/dependency_update_deferrals.json`.

Published image digests live in `docker/image-digests.json`, written only
by the `publish-wire-images.yml` workflow; do not commit
placeholder entries.

## Verification

```bash
uv sync
uv run python scripts/verify_all.py --stage docs       # markdown-only changes
uv run python scripts/verify_all.py --stage fast       # default before PR
uv run python scripts/verify_all.py --stage standard   # contract/gate changes
```

`verify_all.py` runs barrier-marked commands alone and consecutive
non-barrier commands in parallel up to `--jobs` workers; `--list` dumps the
machine-readable command table. pytest runs `-n auto --dist loadgroup`; use
`uv run pytest -n 0` for single-test debugging.

## Git

Write commit messages in English. Do not use `git add .`, amend commits,
`--no-verify`, force push, direct pushes to main, `reset --hard`,
`clean -fd`, `checkout -- file`, or `stash drop`. Do not commit generated
`out/` files, secrets, or environment files. Use `git mv` when renaming
files. Split dependent changes into bottom-up stacked PRs; independent
changes go on separate PRs based on main.

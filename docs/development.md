# Development

## Setup

```bash
uv self update 0.12.23     # [tool.uv] required-version
uv sync --locked
```

Python 3.12 or newer. Text I/O always uses `encoding="utf-8"`.

## Verify

```bash
uv run python scripts/verify_all.py --stage fast       # before every PR
uv run python scripts/verify_all.py --stage standard   # gates, contract or export changes
uv run python scripts/verify_all.py --stage docs       # docs-only changes
uv run python scripts/verify_all.py --list             # every command per stage
```

`fast` runs `uv sync --locked`, `ruff check`, `ruff format --check`,
strict pyright over `src`, `scripts` and `tests`, pytest (xdist) through
`scripts/structural_coverage.py` (C0, C1, decision, C2, MC/DC and boundary
floors; see [test-coverage.md](test-coverage.md)) and
`scripts/verify_docs.py` (Markdown links and the ADR index). `standard`
adds `scripts/check_plugin_load.py` (the plugin loads in the pinned SDK
with the expected skills, agents, commands, hooks and MCP tools) and the
E2E authoring round-trip in the tools image (`scripts/e2e_authoring.py`).

On a Devin VM run pytest as
`env -u BASH_ENV -u "BASH_FUNC_gh%%" uv run pytest` so the shell's `gh`
function does not shadow the stub used by the tests.

## Required CI checks

`verify (3.12)`, `verify (3.13)`, `plugin-load`, `e2e`, `zizmor`. See
[operations.md](operations.md) for release, image publishing and
hardening.

## Rules for changes

- Gates: add a negative test that corrupts the judged input
  (`tests/test_gates.py`) and 3-value boundary tests for every limit.
- Coverage floors in `[tool.vibebb-coverage]` only move up.
- Projections: never edit generated files; change the exporter and its
  tests.
- Schemas: update [contracts.md](contracts.md) and the `wire-contract`
  skill; add or revise an ADR.
- MCP tools, hooks, agents, skills or commands: update the matching page
  ([mcp.md](mcp.md), [hooks.md](hooks.md), [agents.md](agents.md),
  [skills.md](skills.md), [commands.md](commands.md)) and the expected
  lists in `scripts/check_plugin_load.py` / `tests/test_plugin_assets.py`.
- Workflows, scripts and the launcher: grep `tests/` for their literals
  and update the guard test in the same commit.
- Never edit the shared hook canon (`_records.py`, `require_records.py`,
  `ensure_llm_profiles.py`, `safety_rail.py`, `_provenance.py`);
  `scripts/check_shared_hooks.py` fails on any change.

## Module map

| Module | Role |
| --- | --- |
| `contract.py` | `HarnessContract` schema, `contract_sha256` |
| `intake.py` | intake schema and `check_intake` |
| `standards.py` | wire specs, derating, bend factors, connector families |
| `gates.py` | the gate runner (only pass/fail authority) |
| `export.py` | wire list, cut table, BOM, harness diagram, manifest, provenance |
| `route_plan.py` | route plan drawio projection from placed anchors |
| `drawio_cli.py` | drawio-desktop subprocess adapter |
| `drawio_lint.py` | advisory diagram readability lint |
| `render.py` | sha256 visual baseline |
| `advisory.py` | typed visual review records |
| `records.py` | VRP writers and status |
| `liaison.py` | SLP v2 inbox and responder |
| `imports.py` | connectivity / CSV / envelope import |
| `report.py` | design report and vision points |
| `doctor.py` | environment probe |
| `workspace.py` | workspace root and path containment |
| `cli.py` | `python -m wire` |
| `mcp_server.py` | stdio MCP server |

# Contributing

## Setup

```bash
uv sync
uv run python scripts/verify_all.py --stage fast
```

`fast` runs ruff, `ruff format --check`, pyright strict, pytest
(`-n auto --dist loadgroup`), and the docs checks. Use
`--stage docs` for markdown-only changes and `--stage standard` when the
contract schema or gates change.

## Rules of thumb

- `src/wire` is the only pass/fail authority; keep every LLM-facing path
  (skills, agents, MCP tools, hooks) free of verdict logic.
- Artifacts are projections — fix inputs, never generated files.
- Add a negative test that corrupts the judged input whenever you add or
  change a gate (`tests/test_gates.py`).
- Contract schema changes need an ADR or an ADR revision and matching
  updates to `docs/architecture.md` and the `wire-contract` skill.
- English for docs, commits, identifiers; text I/O always
  `encoding="utf-8"`.

See [AGENTS.md](AGENTS.md) for the full working agreement and
[docs/operations.md](docs/operations.md) for dependency and release policy.

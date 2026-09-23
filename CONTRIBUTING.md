# Contributing

Thanks for helping build wire-agent. This repository follows a strict
contract — read [AGENTS.md](AGENTS.md) first; the short version is below.

## Ground rules

- English only: issues, PRs, commits, docs, comments, identifiers
  (README keeps a Japanese appendix).
- `src/wire` is the only pass/fail authority; keep every LLM-facing path
  (skills, agents, MCP tools, hooks) free of verdict logic.
- Artifacts are projections — fix inputs, never generated files.
- Fail-closed: missing tools, parse failures, unexecuted gates, and
  unknowns fail the design.
- Never import-bind GPL/AGPL/LGPL code (copyleft tools run as unmodified
  subprocesses only). Never commit secrets.
- `encoding="utf-8"` on every text read/write.

## Setup

```bash
uv sync
uv run python scripts/verify_all.py --stage fast
```

`fast` runs ruff, `ruff format --check`, pyright strict, pytest
(`-n auto --dist loadgroup`), and the docs checks. Use
`--stage docs` for markdown-only changes and `--stage standard` when the
contract schema or gates change.

## Pull requests

- Keep changes minimal and focused; follow surrounding conventions.
- Add a negative test that corrupts the judged input whenever you add or
  change a gate (`tests/test_gates.py`).
- Contract schema changes need an ADR or an ADR revision and matching
  updates to `docs/architecture.md` and the `wire-contract` skill.
- New dependencies or new external sources must update
  `scripts/check_dependency_updates.py` and its tests in the same change.
- Dependent changes: bottom-up stacked PRs. Independent changes: separate
  PRs on `main`.

## Reporting bugs / requesting features

Open an issue with the harness contract (sanitized) or a minimal
reproducing `*.contract.json` when reporting gate or export bugs. For
security issues use [SECURITY.md](SECURITY.md) instead.

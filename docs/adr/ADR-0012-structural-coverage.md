# ADR-0012: Structural coverage gate (C0, C1, C2, MC/DC, boundaries)

Status: Accepted

## Context

CI measured statement coverage only (`branch = false`, `fail_under = 73`).
Statement and branch coverage cannot show whether each condition of a gate
decision was exercised independently or whether numeric limits were tested
at their boundaries, which is where wire's gates (derating, bend radius,
lengths, pin counts) decide pass or fail. Python has no mature tool for
condition, MC/DC or boundary coverage: `pymcdc` and `mcdc-coverage` have
little use and the latter is not published on PyPI.

## Decision

- Turn on coverage.py branch measurement.
- Add the family-canonical `scripts/structural_coverage.py` (stdlib only, no
  new dependency). It instruments the source AST in memory during the normal
  pytest run and measures decision, C2, MCC, MC/DC (unique-cause with
  short-circuit don't-cares, as GCC and Clang define it for C) and 3-value
  boundary coverage, and reads C0/C1 from coverage.py's JSON.
- Gate six criteria against ratchet floors in `[tool.vibebb-coverage]`;
  MCC is reported only. An unmeasured criterion fails.
- `verify_all.py --stage fast` runs pytest through the script, so CI
  (`verify (3.12)`, `verify (3.13)`) enforces the floors.

See [test-coverage.md](../test-coverage.md).

## Consequences

- Gaps are listed with the evaluation that would close them, which turns
  coverage into concrete test cases.
- The fast stage runs pytest once, as before; instrumentation adds a few
  seconds.
- Code executed only in subprocesses is not observed (same as coverage.py).
- The script and its test are byte-identical across the family; change all
  11 copies together and update the pinned sha256.

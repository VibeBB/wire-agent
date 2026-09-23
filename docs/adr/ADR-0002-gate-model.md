# ADR-0002: Fail-closed deterministic gates; LLM/conversation stay L2

- Status: Accepted
- Date: 2026-09-23

## Context

A harness that passes review on a model's say-so is unsafe: an ampacity or
bend-radius miss becomes a product defect. The family invariant across
mech/circuit/acd/bard is that input files are truth, projections never
flow back, and pass/fail comes only from deterministic gates.

## Decision

Three layers with a hard boundary:

- **L1 authority**: `src/wire` only. `run_gates` returns `GateCheck[]`
  `{id, subject, status, measured, limit, detail}`; a design verdict is
  `pass` iff every check is `pass`. `unknown` and `fail` both fail.
- **L2 steering**: skills, task sub-agents (`wire-brief`, `wire-design`,
  `wire-review`), commands, MCP tools. They may read gate output, propose
  contracts, point at failures, and stop the work — they cannot mark
  anything passed, edit artifacts, or relax a limit.
- **L3 telemetry**: hook logs and status reports. Observe only.

v0.1 gate set (each check is deterministic over the contract):

| Check | Rule |
| --- | --- |
| `connectivity` | every wire endpoint resolves to a declared connector + cavity or a declared splice; every wire's net and route resolve |
| `cavity_occupancy` | a cavity accepts at most one wire |
| `splice_integrity` | every splice joins ≥2 wire legs, all on one net |
| `netlist_coverage` | every declared net is carried by at least one wire |
| `ampacity` | net current ≤ wire ampacity × ambient-temperature derating × bundle derating for the wire's route |
| `voltage_drop` | wire resistance × current over declared length ≤ net drop budget (default 3% of nominal) |
| `insulation_rating` | net voltage ≤ insulation rating; ambient ≤ insulation temperature class |
| `bend_radius` | every route's declared minimum bend radius ≥ wire min-bend factor × outer diameter (worst wire in the bundle) |
| `segregation` | signal classes declared incompatible do not share a route |
| `terminal_compatibility` | wire gauge inside each cavity's accepted range; declared terminal matches the cavity terminal |
| `connector_rating` | per-connector: cavity count within housing, net current/voltage within rating, expected mating cycles within rating, shared housings have distinct keying |
| `manifest_integrity` | every projected artifact's sha256 matches the manifest |

Enforcement rules (same as siblings):

1. The CLI and MCP tools are thin wrappers over `run_gates`; there is no
   "agent verdict" channel.
2. Generated artifacts are write-protected by the `protect-generated`
   pre_tool_use hook (`manifest.json`, `provenance.json`,
   `design-report.json/md`, `wire-list.csv`, `cut-table.csv`, `bom.*`,
   `harness-diagram.drawio.svg`, `kbl.xml`, `vec.xml`); regeneration only via
   `wire_author`/`python -m wire author`.
3. Intake binds provenance: `element_sources` maps every
   connector/net/wire/route to R*/A*/Q*/I* ids, and `check_intake` fails a
   contract whose `contract_sha256` no longer matches.
4. Every measurement is wrapped — exceptions become `unknown`, not
   exceptions-up-the-stack; `unknown` fails the verdict.

## Consequences

A passing verdict is reproducible by any machine with the same contract
bytes. A failed gate always names the exact rule, the measured value, and
the limit so a sub-agent (or human) can repair the contract rather than
weaken the gate.

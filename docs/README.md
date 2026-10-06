# wire-agent documentation

Technical documentation for the wire harness design plugin. The
[README](../README.md) is the user-facing overview; everything here is
for engineers and agents.

## Using and extending the plugin

- [Architecture](architecture.md) — layers, data flow, modules
- [Workflow](workflow.md) — stages, what happens, records left
- [Agents](agents.md) — `wire-brief`, `wire-design`, `wire-review`
- [Skills](skills.md) — every SKILL and what it enforces
- [Commands](commands.md) — slash commands and the `python -m wire` CLI
- [MCP tools](mcp.md) — every tool: inputs, outputs, errors, read/write
- [Hooks](hooks.md) — every hook by event
- [Contracts](contracts.md) — every JSON schema wire reads or writes
- [Records and vision](records-and-vision.md) — VRP for wire, vision points
- [VibeBB Record Protocol](records-protocol.md) — the family protocol
- [Sister cooperation](sister-cooperation.md) — imports, outputs, SLP v2
- [Performance and limits](performance-and-limits.md) — budgets, sandbox, modelling limits

## Running the project

- [Operations](operations.md) — release, images, CI, hardening policy
- [Development](development.md) — setup, verify stages, change rules
- [Test coverage and test design](test-coverage.md) — C0/C1/C2/MCC/MC/DC,
  boundary coverage, floors and test-design techniques
- [Dependency updates](dependency-updates.md) — update policy and deferrals
- [Improvement notes](improvement-notes.md) — done, open and family items

## Research

- [Wire harness domains](research/wire-harness-domains.md) — task taxonomy,
  commercial tools, and standards surveyed before design
- [SDK v1.49.5 feature evaluation](research/sdk-v1.49.5-feature-evaluation.md)
- [SDK v1.49.6 feature evaluation](research/sdk-v1.49.6-feature-evaluation.md)
- [drawio-desktop 31.7.0 feature evaluation](research/drawio-31.7.0-feature-evaluation.md)
- [SDK v1.50.0 feature evaluation](research/sdk-v1.50.0-feature-evaluation.md) —
  SDK, uv, and drawio-desktop update decisions
- [SDK v1.50.1 feature evaluation](research/sdk-v1.50.1-feature-evaluation.md) —
  SDK and tools adoption decisions
- [SDK v1.51.0 feature evaluation](research/sdk-v1.51.0-feature-evaluation.md) —
  SDK, tools, and uv update decisions
- [SDK v1.52.0 feature evaluation](research/sdk-v1.52.0-feature-evaluation.md) —
  SDK and tools adoption decisions

## ADR index

| ADR | Title | Status |
| --- | --- | --- |
| [ADR-0001](adr/ADR-0001-harness-contract.md) | HarnessContract is the single data model and authority | Accepted |
| [ADR-0002](adr/ADR-0002-gate-model.md) | Fail-closed deterministic gates; LLM/conversation stay L2 | Accepted |
| [ADR-0003](adr/ADR-0003-plugin-cooperation.md) | Plugin cooperation via contract files and task delegation | Accepted |
| [ADR-0004](adr/ADR-0004-scope-v01.md) | v0.1 scope — logical layer with declared routes | Accepted |
| [ADR-0005](adr/ADR-0005-intake-attachment-materialization-and-evidence-binding.md) | Intake attachment materialization and evidence binding | Accepted |
| [ADR-0006](adr/ADR-0006-vision-render-and-review-records.md) | Vision render lane, visual baseline, and typed review records | Accepted |
| [ADR-0007](adr/ADR-0007-drawio-sheet-frame.md) | ISO 5457 drawing frame + ISO 7200 title block on the drawio diagram | Accepted |
| [ADR-0008](adr/ADR-0008-attest-published-tools-images.md) | Attest published tools images | Accepted |
| [ADR-0009](adr/ADR-0009-vibebb-record-protocol.md) | VibeBB Record Protocol | Accepted |
| [ADR-0010](adr/ADR-0010-liaison-route-geometry-and-vision-points.md) | SLP v2 responder, anchor geometry and vision points | Accepted |
| [ADR-0012](adr/ADR-0012-structural-coverage.md) | Structural coverage gate (C0, C1, C2, MC/DC, boundaries) | Accepted |

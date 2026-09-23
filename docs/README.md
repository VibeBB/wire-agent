# wire-agent documentation

Specifications and operating policy for the wire harness design agent.
The README is the product overview; this directory holds the authoritative
specifications and design decisions.

## Architecture

- [Architecture](architecture.md) — repository layout, layers, data flow
- [Operations](operations.md) — release, dependency-update, and CI policy

## Research

- [Wire harness domains](research/wire-harness-domains.md) — task taxonomy,
  commercial tools, and standards surveyed before design

## ADR index

| ADR | Title | Status |
| --- | --- | --- |
| [ADR-0001](adr/ADR-0001-harness-contract.md) | HarnessContract is the single data model and authority | Accepted |
| [ADR-0002](adr/ADR-0002-gate-model.md) | Fail-closed deterministic gates; LLM/conversation stay L2 | Accepted |
| [ADR-0003](adr/ADR-0003-plugin-cooperation.md) | Plugin cooperation via contract files and task delegation | Accepted |
| [ADR-0004](adr/ADR-0004-scope-v01.md) | v0.1 scope — logical layer with declared routes | Accepted |

# ADR-0004: v0.1 scope — logical layer with declared routes

- Status: Accepted
- Date: 2026-09-23

## Context

The domain survey ([wire-harness-domains](../research/wire-harness-domains.md))
lists six phases. Building all of them at once would bury the two ideas
that make this agent different (one contract, fail-closed gates) under 3D
geometry and manufacturing-layout work. The first public shape must prove
the contract→gates→projections loop end to end.

## Decision

v0.1 implements:

- `src/wire` deterministic core: `HarnessContract` schema, intake sidecar
  (R*/A*/Q*/I* provenance), the L1 gate set of ADR-0002, projections
  (wire list CSV, cut table CSV, BOM JSON/CSV, harness diagram SVG,
  manifest/provenance, design report JSON/MD), doctor, CLI, and a stdio
  MCP server exposing the same entry points.
- `plugins/wire` OpenHands plugin: `wire-workflow`, `wire-contract`,
  `wire-gates`, `wire-connectivity` skills; `wire-brief`, `wire-design`,
  `wire-review` task sub-agents; `/wire:design`, `/wire:doctor`,
  `/wire:gates`, `/wire:export` commands; session doctor,
  protect-generated, and status hooks.
- Connectivity import adapters for `circuit-json` and generic `csv`
  (ADR-0003).

Explicitly deferred (contract shape already carries room for them):

- 3D routing against an imported mech envelope (`anchor_resolution`
  returns `unknown` until the adapter exists) — v0.3;
- formboard/nailboard flattening and 1:1 layout drawings — v0.2;
- bundle diameter packing — v0.2;
- KBL/VEC export and continuity-tester programs — v0.2;
- splice modeling, fuse coordination tables, backshell/strain-relief
  part modeling — v0.2+.

## Consequences

v0.1 can already design a complete small harness (connectors, nets, wires,
declared routes, segregation, service expectations) and verify it end to
end. Later phases add projections and adapters without touching the
contract's core semantics — growth is additive, not a remodel.

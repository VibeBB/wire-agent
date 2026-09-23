# ADR-0001: HarnessContract is the single data model and authority

- Status: Accepted
- Date: 2026-09-23

## Context

Wire harness design spans six phases (see
[wire-harness-domains](../research/wire-harness-domains.md)): requirements,
logical design, routing, manufacturing, verification, and release.
Commercial tools split these across ECAD, MCAD, and formboard products that
exchange partial models. An agent workflow needs one artifact that is the
source of truth for every phase it owns, and an explicit boundary for the
phases it does not.

The sibling repositories solve this with a machine-readable contract file:
mechanical-agent has `*.brief.json`, electrical-circuit-agent has the
design brief, bard-agent has `song.proposal.json`. wire-agent follows the
same pattern.

## Decision

A single Pydantic-validated JSON file, `<name>.contract.json`, is the
source of truth for a harness. Its schema (`src/wire/contract.py`,
`HarnessContract`) covers phases 0–2 declaration and feeds phases 3–5:

- `connectors` — housings with cavity tables, ratings, keying, sealing;
- `wire_types` — gauge, ampacity + temperature/bundle derating, insulation
  rating and temperature class, minimum bend factor, shielding, flex life;
- `nets` — declared electrical nets with signal class, voltage, current;
- `wires` — endpoint-to-endpoint connections bound to connector cavities
  or splices, nets, routes, lengths, strip lengths, terminal part numbers;
- `splices` — named junction points (`SP<num>`) that merge two or more
  wire legs on one net;
- `routes` — declared segments carrying wires, minimum bend radius, flex
  expectations, protection;
- `segregation` — signal-class separation policies;
- `service` — mating/flex endurance expectations;
- `imported_sources` — provenance for connectivity imported from other
  agents' contracts (see ADR-0003).

Every artifact (wire list, cut table, BOM, harness diagram SVG, tester
data, KBL/VEC export) is a deterministic projection of these bytes and
never flows back. What the contract does not declare — real 3D path
geometry inside the product — is an external input, not an approximation:
phase-2 routing consumes anchor/path declarations, optionally validated
against an envelope contract produced by mechanical-agent.

## Consequences

- One file is both the conversation's output and the gates' input; the
  intake sidecar (`*.intake.json`) binds it to R*/A*/Q* provenance.
- The contract is self-contained: it must not reference, import, or
  require the ACD design graph or any other repository's schema. Adapters
  copy needed values in with provenance instead of linking.
- Contract bytes are diffable and reviewable; the SVG diagram exists so
  humans can review the same content graphically.
- v0.1 implements the logical layer fully and the route layer as declared
  segments; 3D geometry and formboard layout are later projections of the
  same file, not new data models.

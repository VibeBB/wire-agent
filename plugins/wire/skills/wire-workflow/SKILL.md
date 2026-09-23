---
name: wire-workflow
description: Execute a conversational wire harness design workflow with deterministic verification.
version: 0.1.0
license: BSD-3-Clause
triggers:
  - wire harness
  - ワイヤハーネス
  - 配策
  - harness design
  - wire-agent
---

# Wire harness design workflow

Clarify requirements, identify the project directory, then orchestrate the
three sub-agents through the SDK task tools (`TaskToolSet` +
`AgentDefinition` + `TaskTrackerTool`; never DelegateTool or
WorkflowToolSet).

1. `wire-brief` — writes `<name>.contract.json` + `<name>.intake.json`.
   Resolve every `Q*` open question with the user; the intake gate must
   report `ready`.
2. `wire-design` — runs `wire_author`: projections → all deterministic
   gates → `design-report.json`. Failing checks are fixed in the CONTRACT,
   never in the artifacts, until `verdict: pass`.
3. `wire-review` — L2 advisory pass over values, topology, and the SVG
   diagram. Findings feed the contract, never a verdict.

## Domain coverage

- 論理設計 (logical): connectors + cavities, nets, wires, wire types,
  terminal assignment — flagship v0.1 path.
- 経路 (routing): declared route segments with min bend radius, protection,
  flex requirements, anchors — declared, not 3D-computed, in v0.1.
- 分離 (segregation): signal-class separation policies over routes and
  connectors.
- 製造 (manufacturing): wire list, cut table, BOM, harness diagram SVG,
  manifest + provenance — deterministic projections of the contract.

## Boundaries

- The contract and intake are the source of truth; artifacts are
  projections and never flow back into inputs. The `protect-generated`
  hook blocks direct artifact edits.
- Gate JSON is the only pass/fail authority. LLM self-reports, conversation
  text, review findings, and vision observations are never promoted to
  verdicts.
- Missing tools, unreadable artifacts, `unknown` checks → fail-closed.
- Text I/O always `encoding="utf-8"`. Never write secrets anywhere.
- Cooperation with mechanical-agent, electrical-circuit-agent, and
  bard-agent happens through workspace JSON contracts and `task`
  delegation (ADR-0003); wire-agent never imports sibling packages and has
  no acd dependency.

## Imported connectivity

- `wire_import` (and `python -m wire import --from circuit-json|csv|
  mech-envelope`) merges validated source files into the contract and
  records them as `I*` imported sources with sha256. Cite I* ids in the
  intake instead of duplicating imported values as R*/A*.

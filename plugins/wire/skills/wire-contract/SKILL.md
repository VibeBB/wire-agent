---
name: wire-contract
description: Author a HarnessContract contract.json and its intake sidecar.
version: 0.1.0
license: BSD-3-Clause
triggers:
  - harness contract
  - contract.json
  - wire brief
  - ハーネス契約
---

# Harness contract authoring

The contract (`<name>.contract.json`) is the single source of truth. Author
it against `src/wire/contract.py` (`HarnessContract`, `schema_version: 1`)
and validate with `python -m wire intake` or `wire_validate_contract`.

## Element id conventions

| Element | Pattern | Example |
| --- | --- | --- |
| connector | `C<num>` | C1 |
| wire type | `WT<num>` | WT1 |
| net | `N<num>` | N1 |
| wire | `W<num>` | W1 |
| route | `RT<num>` | RT1 |
| route segment | `S<num>` | S1 |
| imported source | `I<num>` | I1 |
| requirement/assumption/question | `R*/A*/Q*` | R1 |

## Field guidance

- **connectors**: give every cavity `accepts_mm2` (min,max) and a terminal
  part number when known; declare `rated_current_a`, `rated_voltage_v`,
  `mating_cycles`, `keying`, `sealed`, `temp_rating_c`. Identical housings
  on one harness need distinct `keying`.
- **wire_types**: prefer a `spec` key from `wire_standards` (AVSS, FLRY-B,
  TXL) to inherit its derating curve, else declare `temp_derating` points
  sorted by temperature. `min_bend_factor` is × outer diameter.
- **nets**: `signal_class` drives segregation and reporting; `voltage_v`,
  `current_a` drive ampacity/drop/insulation/connector gates. Declare
  `max_voltage_drop_v` for 0 V nets (ground returns) and strict budgets.
  `shield_required` forces a shielded wire type; `twisted_pair_with` binds
  two nets to one route.
- **wires**: `route` is required for a passing verdict (bend and
  segregation gates report `unknown` for unrouted wires). `length_m` feeds
  voltage drop; strip lengths and terminals feed the cut table.
- **routes**: every segment needs `min_bend_radius_mm`; `flex_required`
  requires non-static wire classes; `anchors` resolve against an imported
  mech envelope (`anchor_resolution`).
- **segregations**: declare incompatible signal-class pairs; violations
  fail the gate.
- **service**: `mating_cycles` is checked against connector ratings;
  `flex_cycles` is recorded for v0.2 flex-endurance checks.

## Intake sidecar

`<name>.intake.json` binds every element id to source ids:

- `R*` — a requirement the user stated (source `user` or `agent`,
  speaker recorded);
- `A*` — an assumption you made, with `rationale`;
- `Q*` — an open question (blocks `ready` until resolved);
- `I*` — an `imported_sources` entry created by `python -m wire import`.

`check_intake` fails (`blocked`) on sha mismatch (contract edited after
intake), unmapped or unknown elements, unknown source ids, and elements
backed only by assumptions/questions — so every inferred value must be
visible and named.

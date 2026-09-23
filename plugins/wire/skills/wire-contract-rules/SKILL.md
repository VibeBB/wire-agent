---
name: wire-contract-rules
description: Path rule — schema and provenance reminders injected whenever a *.contract.json or *.intake.json file is touched.
version: 0.1.0
license: BSD-3-Clause
paths:
  - "**/*.contract.json"
  - "**/*.intake.json"
---

# Wire contract file rules

- `*.contract.json` follows the `HarnessContract` schema in
  `src/wire/contract.py` (in plugin-only installs, see the canonical sample
  at `plugins/wire/skills/wire-contract/references/example-contract.json`).
  Keep ids stable (`C*`, `WT*`, `N*`, `W*`, `RT*`, `SP*`) — gates and intake
  bindings address them.
- Every element id must be bound in `*.intake.json` to a provenance source:
  `R*` user-stated requirement, `A*` assumption with rationale, `Q*` open
  question, `I*` imported source. Claims read off images are observations —
  A* or Q*, never R*.
- Generated projections (wire lists, cut tables, BOMs, diagrams, manifest,
  provenance, design report, KBL/VEC exports) are never hand-edited —
  change the contract and re-export.

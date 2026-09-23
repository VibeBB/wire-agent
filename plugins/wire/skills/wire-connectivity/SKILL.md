---
name: wire-connectivity
description: Import connectivity and envelope contracts from sibling agents into a harness contract.
version: 0.1.0
license: BSD-3-Clause
triggers:
  - import connectivity
  - circuit import
  - mech envelope
  - 接続情報取り込み
---

# Connectivity and envelope imports

Per ADR-0003, wire-agent cooperates with sibling plugins through JSON
contract files in the shared workspace — never through package imports.
Every import validates the source, copies values into the contract with
`source` provenance, and records the file in `imported_sources` (`I*` ids)
with its sha256.

## circuit connectivity (`*.connectivity.json`)

Shape (validated by `ConnectivitySource` in `src/wire/imports.py`):

```json
{
  "schema_version": 1,
  "system": "circuit",
  "connectors": [
    {"ref": "J2", "family_hint": "JST XH", "housing": "B4B-XH-A",
     "rated_current_a": 3.0, "rated_voltage_v": 250.0,
     "cavities": ["1", "2", "3", "4"]}
  ],
  "nets": [
    {"ref": "+24V", "signal_class": "power", "voltage_v": 24.0,
     "current_a": 2.0}
  ]
}
```

`python -m wire import --contract <file> --source <connectivity.json> --from
circuit-json [--out <file>]` appends new C*/N* ids with `source` refs —
existing elements are never overwritten, and the copy is the truth
(re-import shows a diff, not live coupling). E3-style From/To CSV tables
import through `--from csv` (columns: from_connector, to_connector,
from_cavity, to_cavity, net, signal_class, voltage_v, current_a,
family_hint, housing).

## mech envelope (`*.envelope.json`)

Shape (validated by `EnvelopeSource`):

```json
{
  "schema_version": 1,
  "system": "mech",
  "anchors": [
    {"name": "clip-01", "kind": "clip", "position_mm": [120, 0, 45]}
  ]
}
```

`--from mech-envelope` records the anchors; route `anchors[]` entries then
resolve against them (`anchor_resolution` check). Declaring anchors without
an imported envelope reports `unknown` — fail-closed.

## Intake binding

Imported elements cite their `I*` id in `element_sources` (the import is
the requirement's evidence), not duplicated R*/A* entries. Requirements
the user added on top of imported facts still get their own R*.

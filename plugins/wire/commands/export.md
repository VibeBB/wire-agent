---
description: Export manufacturing projections from a harness contract.
argument-hint: <contract.json> <out_dir>
allowed-tools:
  - terminal
---

Run `python -m wire export --contract <file> --out <dir>` to write
`wire-list.csv`, `cut-table.csv`, `bom.json`, `bom.csv`,
`harness-diagram.drawio.svg`, `manifest.json`, and `provenance.json`.
The `.drawio.svg` is a WireViz-style pin-table diagram that renders as
SVG and embeds the editable drawio model. Export does not judge the
design — run `/wire:gates` or `wire_author` for a verdict.

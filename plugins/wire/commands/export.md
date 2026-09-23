---
description: Export manufacturing projections from a harness contract.
argument-hint: <contract.json> <out_dir>
allowed-tools:
  - terminal
---
Inside OpenHands, wire commands run inside the pinned tools image via the
plugin launcher. Resolve the plugin root the same way the hooks do
(`$WIRE_PLUGIN_ROOT`, `${OPENHANDS_PROJECT_DIR}/plugins/wire`,
`~/.agents/plugins/wire`, `~/.openhands/plugins/installed/wire`) into
`$WIRE_PLUGIN`, then call `python3 "$WIRE_PLUGIN/scripts/wire_launcher.py"
<args>`. In a repo checkout, `uv run python -m wire <args>` is equivalent.


Run `python3 "$WIRE_PLUGIN/scripts/wire_launcher.py" export --contract <file> --out <dir>` to write
`wire-list.csv`, `cut-table.csv`, `bom.json`, `bom.csv`,
`harness-diagram.drawio.svg`, `manifest.json`, and `provenance.json`.
The `.drawio.svg` is a WireViz-style pin-table diagram that renders as
SVG and embeds the editable drawio model. Export does not judge the
design — run `/wire:gates` or `wire_author` for a verdict.

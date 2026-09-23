# Changelog

## [Unreleased]

### Added

- `post_tool_use` provenance hooks (ported from mechanical-agent):
  `record-vision-tool-event` on `inspect_image_with_vision` and
  `record-image-observation` on `file_editor|wire_drawio|wire_export`, writing
  hashed observation records to `.openhands/wire/vision-tool-events.jsonl` and
  `.openhands/wire/image-observations.jsonl`. `wire-review` now declares its
  required hooks in frontmatter (plugin hooks do not propagate to sub-agents).


### Fixed

- `scripts/check_plugin_load.py` now renders the OK summary from the actual
  expected asset sets instead of a hardcoded string that could drift.


### Added

- MCP tool metadata: every `wire_*` tool now carries `annotations.title`
  plus `readOnlyHint` / `destructiveHint` / `idempotentHint` /
  `openWorldHint` so MCP clients (including AgentCanvas) can rank and
  gate tool calls on honest write/read semantics.
- `harness-diagram.drawio.svg` export: WireViz-style pin-table diagram
  rendered as SVG with the editable drawio (diagrams.net) model embedded
  in the root `content` attribute. Wire edges bind to cavity cells and
  carry signal-class colors; shielded wire types render dashed. Replaces
  the flat `harness-diagram.svg` projection.
- `HarnessContract.splices` (`SP<num>`): named junction points; wire
  endpoints are now `{connector, cavity}` XOR `{splice}`. The schema
  change alters `contract_sha256`, so existing `*.intake.json` bindings
  must be regenerated.
- `splice_integrity` gate: a splice joins ≥2 wire legs, all on one net.
- Diagram drawing additions: wire stroke follows the physical insulation
  `color` (WireViz codes, `X/Y` draws a striped overlay; signal-class
  color is the fallback), `twisted_pair_with` draws a dashed band between
  pair midpoints plus a `TP⇄<net>` label suffix, unused cavities are
  greyed, splice nodes draw as labeled dots on a separate `wires` drawio
  layer, and same-connector loops bump off the channel-facing edge.
- `export --png` / `author --png` (and `png: true` on `wire_author`):
  writes `harness-diagram.png`, a 2× raster of the diagram for
  vision-capable reviewers.
- `export --drawio` / `author --drawio` (and `drawio` on `wire_author`):
  comma-listed extra diagram renders (`png`, `jpg`, `pdf`, `html`,
  `svg`, `xml`) through `drawio -x`. `--png` is shorthand for
  `--drawio png`. All render paths run the unmodified drawio-desktop
  binary under `xvfb-run`; the tools image ships a pinned,
  sha256-verified `.deb` plus `fonts-ipafont` for CJK coverage, and the
  renders are review aids — bytes vary with the drawio/font versions,
  so the manifest records actual hashes. Without drawio-desktop the
  `--png`/`--drawio` flags fail closed and the diagram falls back to a
  raw `harness-diagram.drawio` mxfile.
- `wire drawio` command and `wire_drawio` MCP tool: proxy `drawio -x`
  for arbitrary inputs (drawio/vsdx/csv/mermaid) with passthrough
  options (pages, layers, layout, embeds, quality) — the full
  drawio-desktop CLI surface for OpenHands/SDK agents.
- `harness-diagram.drawio.svg` is now rendered by drawio-desktop itself
  (`drawio -x -f svg -e`) when available — canonical rendering with
  drawio's own embedded model — replacing the self-generated embed;
  `provenance.json` records `diagram_renderer`.
- `scripts/check_drawio_export.py` + `verify_all.py --stage drawio`:
  opt-in smoke that exports the example contract through drawio and
  validates the PNG/PDF/XML/drawio-svg bytes (skips when drawio is
  absent; not a gate).
- Vision non-multimodal path: `wire-review` and `wire-brief` declare the
  SDK builtin `inspect_image_with_vision` so a non-vision primary model
  delegates image inspection to a saved vision-capable LLM profile
  (vision stays an L2 aid either way); `think` joins the review tools.
- `wire-contract-rules` path-triggered skill: schema/provenance reminders
  injected whenever a `*.contract.json` / `*.intake.json` file is touched
  (complements the keyword skills; rules and keyword triggers are
  exclusive per skill).
- `wire-contract` skill ships `references/example-contract.json` so a
  plugin-only install carries a canonical sample contract.
- Initial repository scaffold: HarnessContract schema, intake provenance,
  deterministic gates, manufacturing projections, OpenHands plugin
  (`plugins/wire`), CLI/MCP boundary, docs and ADRs.

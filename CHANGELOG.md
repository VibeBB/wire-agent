# Changelog

## [Unreleased]

### Added

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
  vision-capable reviewers. Rasterization shells out to the unmodified
  `rsvg-convert` binary (librsvg: pango/fontconfig resolves CJK glyphs
  and the subprocess boundary keeps its LGPL out of the import set) —
  the tools image ships `librsvg2-bin` plus `fonts-ipafont`; the PNG is
  a review aid — pixel bytes vary with the host's librsvg/font versions.
- Initial repository scaffold: HarnessContract schema, intake provenance,
  deterministic gates, manufacturing projections, OpenHands plugin
  (`plugins/wire`), CLI/MCP boundary, docs and ADRs.

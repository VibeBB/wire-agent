# Changelog

## [Unreleased]

### Added

- `harness-diagram.drawio.svg` export: WireViz-style pin-table diagram
  rendered as SVG with the editable drawio (diagrams.net) model embedded
  in the root `content` attribute. Wire edges bind to cavity cells and
  carry signal-class colors; shielded wire types render dashed. Replaces
  the flat `harness-diagram.svg` projection.
- Initial repository scaffold: HarnessContract schema, intake provenance,
  deterministic gates, manufacturing projections, OpenHands plugin
  (`plugins/wire`), CLI/MCP boundary, docs and ADRs.

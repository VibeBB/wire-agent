# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `wire review-record`: writes `review-visual-<slug>.advisory.json` for a
  reviewed image — computes the image sha256, fills the `vision_review`
  envelope, and validates the detail against `advisory.py` (fail-closed),
  replacing hand-assembled review JSON.
- Harness diagram: connector headers and `bom.json` carry `keying` so
  identical housings are distinguishable on the drawing and the order.
- Harness diagram: pale insulation strokes (white, pale yellow) get a dark
  underlay edge so wires stay visible on the white sheet; LEGEND documents
  the halo and the keying marker.
- `drawio_lint`: `label_on_connector` warning when a wire label's
  estimated box overlaps a connector swimlane.

### Changed

- `cut-table.csv` now lists both ends (`strip_a_mm`/`terminal_a` +
  `strip_b_mm`/`terminal_b`); wires only share a row when both sides match.
- Harness diagram: labels of same-column and loop wires are pushed into
  the routing channel instead of anchoring on the connector boundary.
- Title block Units field reports `px = 0.254 mm` instead of bare `px`.

### Changed

- Docker-only runtime: `wire_launcher.py` no longer falls back to a local
  `docker build` when no pinned image resolves — `$WIRE_TOOLS_IMAGE` or a
  digest lock (`tools-image.json` / `docker/image-digests.json`) is now
  required, and a failed pull is an error (ADR-0003 revision).
- `export_design` fails closed when drawio-desktop/xvfb are absent instead
  of degrading to a raw `harness-diagram.drawio` mxfile — the drawio-rendered
  `.drawio.svg` is the only diagram artifact (drawio ships in the pinned
  wire-tools image). `check_drawio_export.py` and the e2e authoring step run
  inside the locked image via `scripts/run_in_locked_image.py` (also used by
  `verify_all.py --stage drawio`/`standard` and the CI e2e job).
- Drawio-dependent tests skip on hosts without drawio-desktop + xvfb; the
  in-image runs keep the coverage.

### Added

- Vision render lane: `wire_author` and `wire_drawio` (MCP) now attach the
  rendered PNG/JPG inline as `ImageContent` so vision-capable models see the
  drawing directly in the tool result.
- `--baseline` (CLI) / `baseline_path` (MCP) on `author`, `export`, and
  `drawio`: records `image_sha256` on first run and reports
  `match`/`diff` afterwards — a deterministic diagram-change detector
  (`src/wire/render.py`).
- Typed visual review records: `src/wire/advisory.py` ports the circuit
  `AdvisoryResult`/`VisualReviewDetail` contract for
  `review-visual-<slug>.advisory.json`; `wire-review` documents the
  convention (ADR-0006).
- Drawing-quality review: `wire-review` now reviews rendered drawings on
  baseline fidelity (accurate, legible, unambiguous), manufacturing
  completeness (self-sufficient for a no-context shop floor), and design
  intent (dimensioning, layout, linework, topology). `VisualReviewDetail`
  gains a required `impression` field — the reviewer's subjective reading
  of the drawing — and four shared categories: `ambiguous_notation`,
  `missing_dimension`, `missing_manufacturing_info`, `design_intent`.
- `scripts/e2e_authoring.py` requests the PNG render and reports
  `renders`/`render_status` (fail-open when drawio-desktop is absent).
- `harness-diagram.drawio.svg` now projects onto an ISO 5457 / JIS Z 8311
  drawing frame (ADR-0007): the smallest A-series landscape sheet
  (A4–A0, then elongated A0x2 / A0x3, custom beyond) that holds the pin
  table plus the title block, with 20/10 mm borders, centring marks, the
  50 mm zone grid, the size designation, and an ISO 7200 title block on a
  bottom `frame` layer. All title-block values derive from the contract —
  `Date of issue` is `—` because artifacts stay byte-deterministic.
- The diagram now carries a documentation strip below the pin table: a
  LEGEND block explaining the drawing's marks (insulation-color strokes,
  shielded/uncolored wires, unused cavities, splices, twisted-pair bands,
  same-connector loop bumps, wire-label fields) and a numbered NOTES block
  with the manufacturing context a no-context shop floor needs — IPC-A-620
  class, ambient service temperature, units, companion artifacts
  (wire-list/cut-table/bom CSVs), per-route instructions (segment count,
  total length, protection, worst-case bend radius, flex, anchors),
  splices, twisted pairs, shielded nets, service-life cycles, and an
  unused-cavity seal note. All note rows derive from the contract, so the
  strip stays byte-deterministic and always current.
- `post_tool_use` provenance hooks (ported from mechanical-agent):
  `record-vision-tool-event` on `inspect_image_with_vision` and
  `record-image-observation` on `file_editor|wire_drawio|wire_author`, writing
  hashed observation records to `.openhands/wire/vision-tool-events.jsonl` and
  `.openhands/wire/image-observations.jsonl`. `wire-review` now declares its
  required hooks in frontmatter (plugin hooks do not propagate to sub-agents).
- `wire-brief` likewise declares `protect-generated` and
  `record-vision-tool-event` in frontmatter.


### Fixed

- `record-image-observation` matcher now targets `wire_author` (which emits
  the rendered diagram paths) — the previous `wire_export` entry named a
  tool that does not exist, so author-side renders were never logged.
- `drawio_lint` no longer reports floating edges (mxPoint
  `sourcePoint`/`targetPoint` anchors without cell endpoints — the
  twist-pair bands) as `edge_missing_endpoints`, and skips the
  `page_underutilized` warning when a `frame` layer is present.
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

[Unreleased]: https://github.com/VibeBB/wire-agent/commits/main

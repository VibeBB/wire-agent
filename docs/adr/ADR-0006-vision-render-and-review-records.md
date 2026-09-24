# ADR-0006: Vision render lane, visual baseline, and typed review records

## Status

Accepted

## Context

The wire plugin could rasterize `harness-diagram.drawio` to PNG via
drawio-desktop (`--png`), but three gaps kept the vision lane thin:

- `wire_drawio` (and `wire_author` with `png=True`) returned the raster
  only as a path inside a JSON text payload — a vision-capable model had
  to open the file separately rather than seeing the drawing inline in
  the tool result.
- The post_tool_use observation matcher referenced `wire_export`, a tool
  that does not exist, so author-side renders were never logged to
  `image-observations.jsonl`.
- Unlike circuit (`src/circuit/advisory.py`), wire had no typed contract
  for the review record a vision reviewer writes, so findings could not
  be validated or bound to provenance entries.
- There was no deterministic "did the diagram change" answer; a model
  had to compare images by eye.

## Decision

- `wire_author` and `wire_drawio` attach the emitted PNG/JPG inline as
  `types.ImageContent` (base64, `image/png` / `image/jpeg`), following
  the circuit render pattern. The JSON text payload is unchanged — the
  image is an additional content block.
- `src/wire/render.py` adds `record_or_compare_baseline(image_path,
  baseline_path)`: missing baseline writes
  `{image, image_sha256, recorded_at}` and returns `recorded`; an
  existing baseline returns `match`/`diff`; unreadable inputs raise
  `RenderBaselineError` (fail-closed). `--baseline`/`baseline_path` on
  `author`, `export`, and `drawio` wire it into the CLI and MCP.
- `src/wire/advisory.py` ports the circuit `AdvisoryResult` /
  `VisualReviewDetail` contract: `review-visual-<slug>.advisory.json`
  records with a fixed checklist vocabulary (`harness_diagram`,
  `intake_image`), a required `impression` free-text field (the
  reviewer's subjective reading of the drawing — a record without one
  is discarded), finding categories (including the drawing-quality set
  `ambiguous_notation`, `missing_dimension`,
  `missing_manufacturing_info`, `design_intent`), `error`/`warning`/`info`
  severities, and optional normalized bounding boxes. Malformed details
  validate to `None`.
- The record-image-observation matcher is corrected to
  `file_editor|wire_drawio|wire_author`.
- `scripts/e2e_authoring.py` requests the PNG render and reports
  `renders`/`render_status` in its payload; drawio-desktop being absent
  degrades the lane (`render_status: "skipped: ..."`) instead of
  blocking authoring.

## Consequences

- A vision-capable reviewer sees the rendered harness inline in MCP tool
  results — no separate file-open step is needed.
- Image observations now cover every raster the authoring lane produces,
  closing the provenance gap from the dead `wire_export` matcher.
- Visual review findings are typed and validateable; malformed model
  output cannot masquerade as a record.
- Drawio output bytes may vary across drawio versions, so a baseline
  `diff` signals "drawing or toolchain changed" — still a deterministic
  change detector, never a verdict.
- Vision remains L2 advisory: none of these additions feed gate
  verdicts, and the gates' fail-closed model is untouched.

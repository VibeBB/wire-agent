# Improvement notes

Running list kept while reading the repository end to end (AGENTS.md,
README, docs, `src/wire`, `plugins/wire`, tests, workflows) for the
VibeBB family refactor. Each item is marked **done** (landed in this
repository), **open** (stays inside this repository but not done yet) or
**family** (needs a sister plugin or the shared canon).

## Found while reading

1. **done** — `python -m wire import` crashed with
   `AttributeError: 'Namespace' object has no attribute 'out'`: the CLI
   parser never declared `--out` although `cmd_import` reads it.
2. **done** — Re-importing the same source appended a second `I*` entry
   and duplicated every connector and net. Re-import now replaces the
   `imported_sources` entry for the same `(system, ref)` and skips
   elements whose `source.ref` is already present from that system.
3. **done** — Mechanical anchors lost their `kind` and `position_mm` on
   import; only names survived. The contract now keeps anchor geometry
   (`ImportedSource.anchor_points`).
4. **done** — No gate compared a route against the mechanical envelope
   geometry. New `route_geometry` check: a route whose anchors all carry
   positions must be at least as long as the anchor polyline.
5. **done** — Imported sources record a sha256 that was never re-checked.
   New `import_freshness` check fails when the source file changed after
   import and reports `unknown` when it disappeared.
6. **done** — There was no visual of the route/anchor layout, so a vision
   model could only review the pin-table diagram. New `route-plan.drawio.svg`
   (+ PNG) projection and a `route_plan` checklist.
7. **done** — `wire_author` returned the diagram inline only when the
   caller remembered `png: true`. The MCP tool now renders the PNG by
   default and attaches every rendered raster (diagram and route plan).
8. **done** — `record_image_observation.py` did not watch `wire_author`,
   so diagrams returned inline by MCP were never bound to a vision review.
   It now watches `wire_author`, `wire_drawio`, `wire_export`,
   `wire_view_image` and the file editor.
9. **done** — There was no way to put an arbitrary workspace image
   (intake photo, built-harness photo, sister render) in front of the
   model through MCP. New `wire_view_image` tool.
10. **done** — `wire-review` still quoted the old 240-char / two-sentence
    impression rule; the validator enforces 400 chars / three sentences.
11. **done** — The visual-review checklists were only `harness_diagram`
    and `intake_image`; added `route_plan`, `built_harness_photo` and
    `sister_artifact`.
12. **done** — `protect_generated.py` did not protect the hook-written
    `vision-tool-events.jsonl` / `image-observations.jsonl` logs or the
    liaison responses.
13. **done** — The design report did not say which images still need a
    vision review; it now lists `vision_points`.
14. **done** — No SLP v2: `wire_ux_inbox` / `wire_ux_respond` (MCP + CLI)
    with strict local mirrors of the UX-creator request/response schema.
15. **done** — Agent prompts carried a generic "Records you must leave"
    section; they now name wire's stages (`brief`, `design`, `review`,
    `liaison`) and the decisions that need a record.
16. **done** — README mixed user-facing and contributor content; it is
    now a non-engineer guide (English then Japanese) and the technical
    material lives in `docs/`.

## Open inside this repository

- **open** — Route geometry is a lower bound only (straight-line
  polyline). A real 3D routing check needs the mech envelope keep-out
  volumes, which the envelope schema does not carry yet.
- **open** — Formboard (1:1 nail-board) layout and KBL/VEC export remain
  later stages (ADR-0004).
- **open** — Rendered bytes depend on drawio/font versions; baselines are
  sha256 only, without a perceptual diff.

## Family items

- **family** — The mech envelope schema could carry keep-out volumes and
  bend-radius constraints per anchor; wire would consume them directly.
- **family** — UX-creator `build_request` v2 must produce `liaison/`
  files with `inputs[].sha256`; wire's inbox reports `stale` otherwise.
- **family** — See the shared-hook notes in
  [records-and-vision.md](records-and-vision.md#known-canon-behaviour).

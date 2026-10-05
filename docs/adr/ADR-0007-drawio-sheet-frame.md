# ADR-0007: ISO 5457 drawing frame on the drawio diagram

- Status: Accepted
- Date: 2026-09-24

## Context

`harness-diagram.drawio.svg` projected a bare pin table on an ad-hoc
880-px page. A deliverable drawing needs a standard drawing frame （図枠):
border zones, centring marks, a title block, and a sheet-size
designation — the conventions ISO 5457 (identical to JIS Z 8311) and
ISO 7200 define so any reviewer can locate fields and reference zones.

Two constraints shape the design:

- drawio-desktop's SVG export crops to the union of cell bounds (~2 px
  margin), not the declared page — a frame must therefore be ordinary
  cells, sized so the sheet rectangle is the outermost geometry.
- Artifacts are byte-deterministic (identical contract bytes → identical
  artifact bytes), so no wall-clock field may appear.

## Decision

- The diagram gains a bottom `frame` layer (root children in document
  order — `frame` first, then `1` (harness), then `wires`). `pageWidth` /
  `pageHeight` are set to the sheet size so the rendered SVG canvas is the
  sheet itself.
- Sheet size is the smallest ISO A-series landscape sheet (A4–A0, then the
  JIS Z 8311 elongated A0×2 / A0×3) whose drawing space holds the content
  plus the title block; larger content falls back to a custom sheet built
  the same way. px is fixed at 100 px/inch (drawio convention), so
  millimetre rules convert exactly.
- ISO 5457 geometry: 10 mm borders on all four sides — JIS Z 8311 lets an
  unbound sheet omit the 20 mm filing margin, and equal borders keep the
  left and right grid-reference strips the same width; 0.7 mm
  drawing-frame line; 0.35 mm zone ticks; centring marks on all four
  symmetry-axis ends running from the sheet edge to the drawing frame
  only (never into the drawing space, where they would cross content or
  the title block); ~50 mm zone
  fields measured from the sheet symmetry axes with corner fields
  absorbing the remainder, letters (I and O excluded) top-to-bottom on the
  side borders, numerals left-to-right on the top and bottom borders —
  `round(half/50)` per half reproduces Table 2 (A4: 6×4, A3: 8×6,
  A2: 12×8, A1: 16×12, A0: 24×16) and covers custom sheets; the size
  designation sits in the bottom border at the right corner.
- ISO 7200 title block: bottom-right of the drawing space, 180 mm wide,
  in the ISO 7200 / ISO 29845 arrangement (four 9 mm rows, read
  bottom-up):
  - identification row (bottom): revision index, date of issue, language
    code and the sheet number in the bottom-right corner;
  - title row: title (largest text) with the supplementary title below,
    and the identification number (contract id, same size) above the
    identification row;
  - document row: document type, classification/key words and document
    status;
  - administrative row (top): responsible department, technical
    reference, created by, approved by;
  - the legal owner spans the lower three rows down the left edge.
  A technical-data strip above the block carries the harness fields ISO
  7200 §4 keeps out of the title block proper: workmanship standard
  (IPC/WHMA-A-620 class), units, scale and the first 16 hex digits of the
  contract sha256 recorded in the manifest and provenance, which binds
  the printed sheet to its source bytes. The sheet size is not repeated —
  the frame's size designation carries it.
- Values derive from the contract only, never the wall clock. People,
  owner and release data come from the optional `drawing` block
  (`DrawingInfo`); unset fields print `—` and the creator falls back to
  `wire-agent/<version>`. The document status is derived, not declared:
  `In preparation` without an approver, `In approval` with one, and
  `Released` once `date_of_issue` is also set — a date of issue without
  an approver is rejected, so an unapproved sheet can never look issued.
  Values that would overflow their cell shrink to 6 pt, then truncate
  with an ellipsis; they never spill over a rule.
- Compared with KiCad's default drawing sheet (title, company, size,
  date, rev, id, file, sheet path, four comments) the block adopts the
  emphasised title and identification number and a source binding
  (contract digest instead of a file name), and adds the approval and
  status fields KiCad lacks; it drops the size field and free comments
  (the drawing's notes block carries those).
- Logos. The legal owner's logo is optional: `drawing.owner_logo`
  names an SVG or PNG relative to the contract directory together with
  its sha256 (≤256 KiB). The export resolves it under that directory and
  fails closed on a missing file, a path escape or a digest mismatch,
  then embeds it as a data URI in the upper part of the Legal owner cell
  above the owner name. Because the pin lives in the contract, swapping
  the file changes nothing silently — it stops the export. The VibeBB
  mark is a producer mark, not an owner mark: it is printed small in the
  bottom border, centred between the first zone numeral and the first
  zone tick, outside the drawing space and the title block. Its geometry
  (`src/wire/mark.py`) is the `silkscreen` group of
  `assets/vibebb-silkscreen.svg` in VibeBB/www.vibebb.org at commit
  2ad2267, recoloured black with the board-preview plate dropped; it is
  pure stroke paths, so it renders without fonts and byte-identically.
- The `frame` layer cell carries `locked=1`, so drawio shows it locked
  and a hand edit cannot move the border or title block.
- `drawio_lint` treats the `frame` layer as outside content checks (it
  already only inspects `parent="1"` vertices) and skips the
  `page_underutilized` coverage warning when a frame layer exists — the
  sheet is intentionally mostly frame. The lint also learned floating
  edges (mxPoint `sourcePoint`/`targetPoint`, no cell endpoints) so the
  twist-pair bands it used to flag as `edge_missing_endpoints` are
  recognised as valid.

## Consequences

- Every projection now ships on a standards-shaped sheet at A4 minimum;
  large harnesses grow through the sheet ladder automatically.
- The frame is a projection like the rest — regenerated, never edited;
  changes land in `export.py`.
- Releasing a drawing is a contract edit (`drawing.approved_by` plus
  `drawing.date_of_issue`), so the release is hashed, re-gated and
  visible in provenance like any other change.

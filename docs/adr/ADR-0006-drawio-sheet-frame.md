# ADR-0006: ISO 5457 drawing frame on the drawio diagram

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
- ISO 5457 geometry: 20 mm left filing border, 10 mm elsewhere; 0.7 mm
  drawing-frame line; 0.35 mm zone ticks; centring marks on all four
  symmetry-axis ends reaching 10 mm into the drawing space; ~50 mm zone
  fields measured from the sheet symmetry axes with corner fields
  absorbing the remainder, letters (I and O excluded) top-to-bottom on the
  side borders, numerals left-to-right on the top and bottom borders —
  `round(half/50)` per half reproduces Table 2 (A4: 6×4, A3: 8×6,
  A2: 12×8, A1: 16×12, A0: 24×16) and covers custom sheets; the size
  designation sits in the bottom border at the right corner.
- ISO 7200 title block: bottom-right of the drawing space, ~180 mm ×
  3 rows × 4 columns — legal owner, title, drawing number, revision index,
  scale, segment/sheet number, size, IPC class, drawn-by, document type,
  date of issue, units. Every value derives from the contract; `Date of
  issue` is rendered `—` because a deterministic artifact cannot carry a
  wall-clock date.
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
- `Date of issue` stays `—` until provenance carries a real issue date
  (e.g. an intake field) that still hashes deterministically.

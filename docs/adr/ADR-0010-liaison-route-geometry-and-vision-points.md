# ADR-0010: SLP v2 responder, anchor geometry and vision points

## Status

Accepted

## Context

The VibeBB family refactor (2026-10-05) makes UX-creator the director of
all sister plugins through the Sister Liaison Protocol (SLP) v2, asks for
vision review at every artifact a model can look at, and allows breaking
changes. wire had three gaps: no way to read or answer UX-creator
requests; mech envelope imports dropped anchor positions, so routes were
never compared with the mechanical layout; and only the harness diagram
was rendered for review. Re-importing a changed envelope also appended
duplicate sources instead of refreshing them.

## Decision

- Add `src/wire/liaison.py` with strict SLP v2 models, an inbox
  (`new`/`answered`/`stale`/`blocked` plus malformed files) and a
  responder that hashes inputs and artifacts, takes gate verdicts from
  design reports, checks VRP references, and refuses `done` while any
  gate is `fail`/`unknown`, the request is stale or dependencies are
  unanswered. Exposed as `wire_ux_inbox` / `wire_ux_respond` and
  `wire ux inbox|respond`.
- Keep anchor kind and `position_mm` from mech envelopes in
  `ImportedSource.anchor_points`; re-imports replace the entry for the
  same `(system, ref)`.
- Add two gates: `route_geometry` (route length must cover the polyline
  through its placed anchors; `unknown` when a route has anchors but some
  are unplaced) and `import_freshness` (the recorded sha256 of every
  imported file must match the file on disk).
- Render `route-plan.drawio.svg` / `route-plan.png` when anchors are
  placed, return it inline from `wire_author`, list rendered rasters in
  `design-report.json` `vision_points`, add `wire_view_image` for any
  workspace image, and log image observations from `wire_author`,
  `wire_drawio` and `wire_view_image` so the Stop hook owes a vision
  review for each.
- Raise the typed advisory impression floor to the VRP floor (400
  characters, three sentences) and add the `route_plan`,
  `built_harness_photo` and `sister_artifact` checklists.

## Consequences

- Contracts that list anchors without positions get `unknown` from
  `route_geometry` once a mech import with positions exists for some of
  them; designers must import the envelope or remove the anchors.
- Old 240-character advisory records no longer validate (backward
  compatibility was waived for this refactor).
- Liaison responses are protected projections like the other artifacts.

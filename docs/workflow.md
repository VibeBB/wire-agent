# Workflow

A wire design runs as four stages driven by the `wire-workflow` skill (or
`/wire:design`). Each stage is a task sub-agent started through the SDK
`TaskToolSet`; the deterministic gates in `src/wire/gates.py` decide pass
or fail, and every stage leaves VibeBB Record Protocol (VRP) records.

| Stage | Who | Input | Output | Records left |
| --- | --- | --- | --- | --- |
| 0. Liaison check | orchestrator | `liaison/*.ux-request.json` | inbox states | — |
| 1. Brief | `wire-brief` | conversation, images, sister exports, UX requests | `<name>.contract.json`, `<name>.intake.json` (`ready`) | decisions, `brief` impression, vision reviews for intake images |
| 2. Design | `wire-design` | ready contract | `out/<name>/` projections, `design-report.json/.md` | decisions per repair, `design` impression, vision reviews for each render |
| 3. Review | `wire-review` | export directory | `review-visual-*.advisory.json`, findings | vision reviews, `review` impression |
| 4. Liaison answer | orchestrator | inbox entries | `liaison/*.ux-response.json` | `liaison` impression referenced by the response |

## 0. Liaison check

`wire_ux_inbox` lists UX-creator requests addressed to wire with a state
(`new`, `answered`, `stale`, `blocked`) and every malformed liaison file.
`new` and `stale` requests become input to the brief. See
[sister-cooperation.md](sister-cooperation.md).

## 1. Brief

`wire-brief` clarifies electrical (nets, classes, voltage, current,
shielding, twisted pairs), environmental (ambient, sealing, flex) and
mechanical (routes, protection, anchors) requirements. Sister exports are
merged with `wire_import`: circuit connectivity (`circuit-json`), generic
CSV tables (`csv`) and mech envelopes (`mech-envelope`). Images (pinout
photos, sketches) are viewed directly, through `wire_view_image`, or via
`inspect_image_with_vision`; anything read off an image becomes an `A*`
assumption or a `Q*` question, never an `R*` requirement. The intake gate
(`wire_intake`) must report `ready` before the design stage starts.

## 2. Design

`wire-design` calls `wire_author`: export projections, run every gate,
write the report. `png` defaults to true over MCP, so the harness diagram
and (when anchor positions exist) the route plan come back inline. Each
`fail` or `unknown` check is fixed in the contract and the stage reruns.
The report lists `vision_points`: the rasters that need a vision review.

## 3. Review

`wire-review` reads values and topology, then inspects every raster with
its checklist (`harness_diagram`, `route_plan`, `intake_image`,
`built_harness_photo`, `sister_artifact`) and writes typed
`review-visual-<slug>.advisory.json` records with `review-record`, plus a
`wire_record_vision_review` per image. Findings feed the contract; they
never change a verdict.

## 4. Liaison answer

`wire_ux_respond` writes the response with hashed inputs and artifacts,
gate verdicts taken from `design-report.json`, and references to VRP
decisions and impressions. `done` is refused while any gate is `fail` or
`unknown`.

## Stop

The `require-records` Stop hook refuses to end a session that still owes
a decision, a fresh stage impression for changed artifacts, or a vision
review for a viewed image ([hooks.md](hooks.md)). The `report-design-status`
hook prints the latest gate verdicts.

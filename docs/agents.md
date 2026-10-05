# Agents

Three task sub-agents live in `plugins/wire/agents/`. Each declares its
own MCP config (the `wire` server through `wire_launcher.py`) and its own
hooks, because plugin hooks do not propagate into task sub-agents. All run
with `permission_mode: never_confirm` (see [operations.md](operations.md)).

| Agent | Model profile | Tools | Hooks declared | Budget |
| --- | --- | --- | --- | --- |
| `wire-brief` | `vibebb-author` | terminal, file_editor, grep, glob, task_tracker, `VisionInspectTool` | protect-generated, safety-rail, record-vision-tool-event | 40 iterations, 3.0 USD |
| `wire-design` | `vibebb-author` | terminal, file_editor, grep, glob, task_tracker | protect-generated, safety-rail | 40 iterations, 3.0 USD |
| `wire-review` | `vibebb-review` | terminal, file_editor, grep, glob, `VisionInspectTool`, `ThinkTool` | protect-generated, safety-rail, record-vision-tool-event | 30 iterations, 2.0 USD |

## wire-brief

Intake sub-agent. Step 0 reads the UX liaison inbox and imports sister
exports with `wire_import`. It then clarifies requirements, writes
`<name>.contract.json` (schema in [contracts.md](contracts.md)) and
`<name>.intake.json` binding every element id to `R*`/`A*`/`Q*`/`I*`
ids, and loops until the intake gate reports `ready`. Claims read from
images are `A*` or `Q*` only.

## wire-design

Authoring sub-agent. Runs `wire_author`, reads `design-report.json`,
repairs the contract for every `fail`/`unknown` check, and reruns until
the verdict is `pass` or a named check cannot pass under the current
requirements. Looks at each inline render and records a vision review.
Never edits projections and never relaxes a limit.

## wire-review

L2 advisory reviewer. Checks values and topology, then reviews every
raster listed under `vision_points` on three drawing axes (baseline
fidelity, manufacturing completeness, design intent) plus the
route-plan checks (anchor order, `TOO SHORT` legends, anchor kinds,
agreement with the mechanical layout). Writes typed advisory records via
`review-record` and a VRP vision review per image. Impressions are at
least 400 characters and three sentences.

## Records

Every agent carries the "Records you must leave" section: a decision for
each non-trivial choice, a stage impression after the final regeneration
and a vision review for every image looked at
([records-and-vision.md](records-and-vision.md)).

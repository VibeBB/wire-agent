---
description: Orchestrate a conversational wire harness design workflow.
argument-hint: <project_dir> <requirements summary>
allowed-tools:
  - task_tracker
  - task_tool_set
  - terminal
---

First call `wire_ux_inbox`: every `new` or `stale` UX-creator request for
wire is part of this job. Clarify requirements with the user, create a
task-tracker plan, then delegate first to `wire-brief`. Resolve every returned `open_questions` item with the
user and repeat until the intake verdict is `ready`. Only then delegate to
`wire-design` and `wire-review` through the SDK task tool set. The JSON gate
verdicts, not a sub-agent opinion, determine pass or fail.

Use `TaskToolSet`, `AgentDefinition`, and `TaskTrackerTool`; do not use the
deprecated DelegateTool or WorkflowToolSet.

`wire-brief` writes `<name>.contract.json` plus `<name>.intake.json`. The
contract declares connectors (cavities, ratings, keying), wire types (gauge,
ampacity + derating, insulation, bend factor), nets (signal class, voltage,
current, twisted pairs, shield requirements), wires (connector-cavity or
splice endpoints, insulation `color` codes, length, terminals), splices,
routes (segments with declared min bend radius, protection), segregations,
and service expectations. A blocked intake stops delegation — never hand an unready
contract to `wire-design`.

Then delegate to `wire-design`: it runs `wire_author` (export wire list, cut
table, BOM, diagram → run every gate → write `design-report.json`), reads
each failing check, fixes the CONTRACT, and reruns. Artifacts are
projections — never edit generated files, never weaken a limit to pass.

Finally — required, never skipped — delegate to `wire-review` for an
advisory pass over values, topology, and the rendered diagram. Every
rendered image in the export directory must be vision-inspected and get
a `review-visual-*.advisory.json` record with a substantive multi-sentence
impression (the validator rejects terse records); an unreviewed raster is
unfinished work. Findings feed the contract, never a verdict.

Answer each liaison request with `wire_ux_respond` (artifacts, the
`design-report.json` path, decision and impression event ids); `done` is
refused while a gate fails, so answer `needs_info`, `deferred` or
`rejected` with a reason instead.

Summarize for the user: the final `verdict`, each failing gate by id if any,
the artifact directory, and open follow-ups (3D keep-out routing, formboard
layout, KBL/VEC export left to later stages) and the liaison answers.

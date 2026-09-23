---
description: Orchestrate a conversational wire harness design workflow.
argument-hint: <project_dir> <requirements summary>
allowed-tools:
  - task_tracker
  - task_tool_set
  - terminal
---

Clarify requirements with the user, create a task-tracker plan, then delegate
first to `wire-brief`. Resolve every returned `open_questions` item with the
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

Finally delegate to `wire-review` for an advisory pass over values, topology,
and the SVG diagram. Findings feed the contract, never a verdict.

Summarize for the user: the final `verdict`, each failing gate by id if any,
the artifact directory, and open follow-ups (3D envelope routing, formboard
layout, KBL/VEC export left to later stages).

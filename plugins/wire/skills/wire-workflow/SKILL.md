---
name: wire-workflow
description: Execute a conversational wire harness design workflow with deterministic verification.
version: 0.1.0
license: BSD-3-Clause
triggers:
  - wire harness
  - ワイヤハーネス
  - 配策
  - harness design
  - wire-agent
---

# Wire harness design workflow

Clarify requirements, identify the project directory, then orchestrate the
three sub-agents through the SDK task tools (`TaskToolSet` +
`AgentDefinition` + `TaskTrackerTool`; never DelegateTool or
WorkflowToolSet).

Inside OpenHands, wire commands run inside the pinned tools image via the
plugin launcher. Resolve the plugin root the same way the hooks do
(`$WIRE_PLUGIN_ROOT`, `${OPENHANDS_PROJECT_DIR}/plugins/wire`,
`~/.agents/plugins/wire`, `~/.openhands/plugins/installed/wire`) into
`$WIRE_PLUGIN`, then call `python3 "$WIRE_PLUGIN/scripts/wire_launcher.py"
<args>`. In a repo checkout, `uv run python -m wire <args>` is equivalent.

1. `wire-brief` — writes `<name>.contract.json` + `<name>.intake.json`.
   Resolve every `Q*` open question with the user; the intake gate must
   report `ready`.
2. `wire-design` — runs `wire_author`: projections → all deterministic
   gates → `design-report.json`. Failing checks are fixed in the CONTRACT,
   never in the artifacts, until `verdict: pass`.
3. `wire-review` — L2 advisory pass over values, topology, and the
   diagram. Findings feed the contract, never a verdict.
4. Liaison — when the workspace has a `liaison/` directory, answer every
   UX-creator request addressed to wire (see "UX-creator liaison" below).

## UX-creator liaison (SLP v2)

UX-creator writes `liaison/<id>.ux-request.json`; wire answers with
`liaison/<id>.ux-response.json`. At session start and before the final
answer, call `wire_ux_inbox` (`python -m wire ux inbox`): it lists each
request for wire with a `state` — `new`, `answered`, `stale` (an input
changed since the request or since the response), `blocked` (a
`depends_on` request is unanswered) — and every malformed liaison file.

- Work `new` requests through the normal brief → design → review stages;
  the request's `requested_changes`, `expected_deliverables` and
  `acceptance` become intake requirements.
- Answer with `wire_ux_respond` (`python -m wire ux respond --json f`):
  give `request`, `status`, `reason`, the delivered `artifacts`, the
  `design_reports` whose checks become `gate_verdicts`, and the VRP
  `decision_refs` / `impression_refs` (event_ids from `wire_record_*`).
  The writer hashes the inputs and artifacts itself.
- `done` is refused while any gate is `fail`/`unknown`, while the request
  is stale or blocked, without artifacts, or without an impression ref:
  answer `needs_info` (with `questions_for_user`) or `rejected` with a
  20+ character reason instead. Never hand-edit a response file (the
  `protect-generated` hook blocks it).
- Re-answer `stale` requests after re-running the affected stages.

## Vision uses (L2 only)

Vision is welcome at three points — every vision output stays an L2
steering aid, never a verdict. When the model does not support image
input, `inspect_image_with_vision` (spec name `VisionInspectTool`)
delegates to a saved vision-capable LLM profile instead (no such profile
→ skip vision entirely rather than guess) — and it inspects only images
attached to the latest user message, so it covers intake and
user-provided harness photos, not workspace renders like
`harness-diagram.png`:

- **Intake**: user-supplied pinout photos, datasheet tables, or wiring
  sketches can seed connector/cavity/wire candidates. The
  `intake-attachments` hook materializes attached images to
  `intake/attachments/<sha256[:12]>.<ext>` with a `manifest.jsonl`
  provenance record; an A* or Q* record can bind one of those files via
  its optional `evidence` field (`kind`, `path`, `sha256`, `note`) and
  `check_intake` verifies the bytes — fail-closed. Claims read off an
  image land in the intake as A* (rationale attached) or Q* — never R*.
- **Diagram review**: `python3 "$WIRE_PLUGIN/scripts/wire_launcher.py" export --png` writes
  `harness-diagram.png`, a drawio-desktop render the FileEditorTool can
  send to the vision model. Check legibility and topology against the
  legend in `plugins/wire/agents/wire-review.md`, plus its
  drawing-quality axes (baseline fidelity, manufacturing completeness,
  design intent) and the mandatory `impression` on every record.
  `--drawio` takes more
  formats (jpg, pdf, html, svg, xml); `wire_drawio` / `python -m wire
  drawio` expose the full `drawio -x` surface for arbitrary inputs.
- **Route plan**: when imported mech anchors carry `position_mm`,
  `wire_author` also renders `route-plan.png` (top view of anchors and
  route polylines with length vs anchor span). Review it with the
  `route_plan` checklist; `route_geometry` is the gate on the same data.
- **Any workspace image**: `wire_view_image` returns a PNG/JPEG inline
  (sister renders, built-harness photos) so a vision-capable model sees
  it without the file editor.
- **Manufactured-harness crosscheck**: a photo of a built harness vs the
  PNG can flag obvious mismatches (missing cavity population, wrong
  insulation color) as observations for the user — the contract is not
  edited from photos.

## Domain coverage

- 論理設計 (logical): connectors + cavities, nets, wires, wire types,
  terminal assignment — flagship v0.1 path.
- 経路 (routing): declared route segments with min bend radius, protection,
  flex requirements, anchors — declared, not 3D-computed. Anchor positions
  imported from a mech envelope feed the `route_geometry` gate (route
  length must cover the anchor polyline) and the route plan render.
- 分離 (segregation): signal-class separation policies over routes and
  connectors.
- 製造 (manufacturing): wire list, cut table, BOM, harness diagram
  (`.drawio.svg` rendered by drawio-desktop, `.drawio` mxfile without
  it, plus `--drawio` png/jpg/pdf/html/svg/xml review renders),
  manifest + provenance — deterministic projections of the contract.
  The diagram is self-documenting: ISO 5457 frame + ISO 7200 title block,
  a LEGEND block (wire colors, shield dashes, splices, twist bands), and
  a numbered NOTES block (IPC class, units, route/bend/protection
  instructions, splices, service life) generated from the contract.

## Boundaries

- The contract and intake are the source of truth; artifacts are
  projections and never flow back into inputs. The `protect-generated`
  hook blocks direct artifact edits.
- Gate JSON is the only pass/fail authority. LLM self-reports, conversation
  text, review findings, and vision observations are never promoted to
  verdicts.
- Missing tools, unreadable artifacts, `unknown` checks → fail-closed.
- Text I/O always `encoding="utf-8"`. Never write secrets anywhere.
- Cooperation with mechanical-agent, electrical-circuit-agent, and
  bard-agent happens through workspace JSON contracts and `task`
  delegation (ADR-0003); wire-agent never imports sibling packages and has
  no acd dependency.

## Imported connectivity

- `wire_import` (and `python3 "$WIRE_PLUGIN/scripts/wire_launcher.py" import --from circuit-json|csv|
  mech-envelope`) merges validated source files into the contract and
  records them as `I*` imported sources with sha256. Cite I* ids in the
  intake instead of duplicating imported values as R*/A*. Without
  `out_path`, the merged contract is written to
  `<contract-stem>.merged.contract.json` next to the contract.
- Re-importing the same source refreshes its `I*` entry (new sha256,
  anchors and anchor geometry) and appends only connectors/nets whose
  refs are new. The `import_freshness` gate fails when a recorded source
  file changed after the import, so re-import instead of editing hashes.

## Terminal tool notes

The terminal tool runs **one command per call**: a payload carrying several commands is bounced
as "Cannot execute multiple commands at once". Chain with `&&` inside a single command when you
need two steps, and write files with `file_editor` rather than multi-line heredocs.

## Records you must leave (VibeBB Record Protocol — mandatory, unprompted)

Record these without being asked; the Stop hook refuses to finish a
session that still owes them (see `docs/records-protocol.md`).

- **Decision** (`wire_record_decision`) for every non-trivial choice:
  the question, the first principles / physical laws / standards it rests
  on, at least two options with pros and cons, the chosen option, a
  rationale of 200+ characters, evidence (artifact paths are hashed; cite
  datasheets or standards as references), assumptions, unknowns, residual
  risks and the observation that would reopen it. Reason from principles,
  not from habit.
- **Stage impression** (`wire_record_impression`) when a stage ends,
  after its final regeneration: 400+ characters and 3+ sentences on what
  you noticed, what works, what worries you, how a maker or user would
  read the result, and what to do next. List the stage's output files or
  directories so the impression is bound to their sha256.
- **Vision review** (`wire_record_vision_review`) every time you look
  at an image (a rendered drawing, a photo, a screenshot, an
  `inspect_image_with_vision` answer): findings plus a long-form
  impression of 400+ characters judging accuracy, ambiguity, whether the
  design intent comes across and whether the shop floor could act on it —
  not only legibility. Bind it to `image_path` or to the vision event's
  `source_event_id`.

Vision and impressions are advisory: they never override a deterministic
gate verdict. Results do not have to be identical from run to run; the
reasoning must be recorded every run. `wire_records_status` shows what is
still owed.

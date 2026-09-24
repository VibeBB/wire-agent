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
  legend in `plugins/wire/agents/wire-review.md`. `--drawio` takes more
  formats (jpg, pdf, html, svg, xml); `wire_drawio` / `python -m wire
  drawio` expose the full `drawio -x` surface for arbitrary inputs.
- **Manufactured-harness crosscheck**: a photo of a built harness vs the
  PNG can flag obvious mismatches (missing cavity population, wrong
  insulation color) as observations for the user — the contract is not
  edited from photos.

## Domain coverage

- 論理設計 (logical): connectors + cavities, nets, wires, wire types,
  terminal assignment — flagship v0.1 path.
- 経路 (routing): declared route segments with min bend radius, protection,
  flex requirements, anchors — declared, not 3D-computed, in v0.1.
- 分離 (segregation): signal-class separation policies over routes and
  connectors.
- 製造 (manufacturing): wire list, cut table, BOM, harness diagram
  (`.drawio.svg` rendered by drawio-desktop, `.drawio` mxfile without
  it, plus `--drawio` png/jpg/pdf/html/svg/xml review renders),
  manifest + provenance — deterministic projections of the contract.

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

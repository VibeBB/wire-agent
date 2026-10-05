# Architecture

wire-agent is an OpenHands plugin for conversational wire harness design:
requirements → harness contract → deterministic gates → manufacturing
projections. It follows the family pattern of mechanical-agent and
electrical-circuit-agent: a deterministic Python core owns truth and
verdicts; the plugin layer only steers.

## Layers

```text
L1  src/wire/            deterministic core — sole pass/fail authority
L2  plugins/wire/        OpenHands plugin — steering, never verdicts
L3  hooks/telemetry      observation only
```

- **L1** (`src/wire`): `HarnessContract` schema, intake provenance,
  standards tables, gate runner, exporters, report, doctor, CLI, and the
  stdio MCP boundary. Pure deterministic code; no LLM paths.
- **L2** (`plugins/wire`): skills, task sub-agents, commands, hooks.
  Sub-agents author and repair the contract JSON; the gates decide.
- **L3**: hook scripts record status; nothing reads them for verdicts.

## Data flow

```text
conversation ──▶ <name>.contract.json + <name>.intake.json   (truth)
                        │
        python -m wire author / wire_author (MCP)
                        │
        ┌───────────────┼───────────────────┐
        ▼               ▼                   ▼
   run_gates       export              design-report
   (L1 verdict)    wire-list.csv       .json / .md
                   cut-table.csv
                   bom.json/.csv
                   harness-diagram.drawio.svg (ISO 5457 frame + ISO 7200 title block)
                   harness-diagram.drawio_lint.json (advisory)
                   harness-diagram.png (vision render)
                   route-plan.drawio.svg / .png (placed mech anchors)
                   manifest.json / provenance.json

liaison/<id>.ux-request.json ──▶ wire_ux_inbox ──▶ stages ──▶ wire_ux_respond
                                                             └▶ liaison/<id>.ux-response.json
mech *.envelope.json / circuit connectivity ──▶ wire_import ──▶ contract (I* sources)
every viewed image / stage end / choice ──▶ observations/wire/*.jsonl (VRP)
```

Gate verdicts are the only pass/fail authority; `unknown` fails closed.
Artifacts are projections — the `protect-generated` hook blocks direct
edits; repair happens in the contract.

## Repository layout

```text
src/wire/
├── contract.py           # HarnessContract schema (truth source)
├── intake.py             # intake/provenance schema + coverage check
├── standards.py          # wire specs, derating, bend factors, families
├── gates.py              # authoritative gate runner
├── export.py             # projections + manifest/provenance
├── drawio_lint.py        # advisory drawio readability lint (never a verdict)
├── route_plan.py         # route plan projection from placed anchors
├── drawio_cli.py         # drawio-desktop subprocess adapter
├── render.py             # sha256 visual baseline
├── advisory.py           # typed visual review records
├── records.py            # VRP writers and status
├── liaison.py            # SLP v2 inbox and responder
├── workspace.py          # workspace root + path containment
├── report.py             # design-report.json/md + vision points
├── doctor.py             # environment probe
├── imports.py            # connectivity/envelope import adapters
├── cli.py                # python -m wire {doctor,intake,author,gates,export,drawio,drawio-lint,import,review-record,record,ux}
└── mcp_server.py         # stdio MCP boundary
plugins/wire/
├── .plugin/plugin.json
├── .mcp.json             # wire MCP server registration
├── skills/               # wire-workflow, wire-contract, wire-gates,
│                         # wire-connectivity
├── agents/               # wire-brief, wire-design, wire-review
├── commands/             # /wire:design, /wire:doctor, /wire:gates, /wire:export
├── hooks/                # doctor, attachments, profiles, records, artifact guard,
│                         # safety rail, vision/image observation, status report
└── scripts/wire_launcher.py
tests/                    # schema, gates (+negative), export, intake, plugin assets
scripts/                  # verify_all, verify_docs, check_plugin_load, e2e
examples/                 # small harness contract used by docs and tests
docs/adr/  docs/research/  docs/operations.md
docker/                   # wire-tools image definition + digest lock
```

## Cooperation model

Per ADR-0003, wire-agent interoperates with its sister plugins through
JSON files in the shared workspace plus `task`-tool delegation — never
package imports. UX-creator directs the family through SLP v2 liaison
files (ADR-0010, [sister-cooperation.md](sister-cooperation.md)).
There is no acd-agent dependency anywhere in the repository.

## Determinism rules

- Same contract bytes → same artifact bytes: sorted keys, stable ordering
  by declared ids, no wall-clock fields in projections.
- Text I/O always `encoding="utf-8"`.
- `python -m wire` and the MCP tools share the same functions; outputs are
  identical JSON payloads.
- Inside OpenHands, `plugins/wire/scripts/wire_launcher.py` is the single
  exec point: hooks and the MCP server call it, and it runs the module
  inside the pinned `wire-tools` image (source mounted at `/plugin-src`,
  the workspace bind-mounted at its own path). Host Python only needs to
  launch docker.

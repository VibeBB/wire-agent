# ADR-0003: Plugin cooperation via contract files and task delegation

- Status: Accepted
- Date: 2026-09-23

## Context

wire-agent must operate alongside mechanical-agent, electrical-circuit-
agent, and bard-agent, and must not depend on acd-agent. OpenHands SDK
v1.49.4 offers no typed plugin-to-plugin API. What exists:

- `load_plugins` merges several plugins into one conversation (skills
  merge last-wins, `mcp_config` merges, hooks concatenate);
- `register_plugin_agents` puts every plugin's AgentDefinitions into the
  delegate registry, callable through the `task` tool;
- every plugin's MCP tools are callable by any agent;
- the shared workspace persists files visible to all plugins.

The cooperation channel is therefore the one the family already uses:
JSON contract files in the workspace, exchanged deterministically, with
provenance recorded. wire-agent does not read sibling repositories and
does not import their packages.

## Decision

Three boundary contracts, each a plain JSON file in the project directory:

### Inbound: connectivity (`*.connectivity.json`, source `circuit`)

electrical-circuit-agent exports a normalized connectivity view:
`{connectors: [{ref, cavities: [{id, accepts_mm2}], family_hint,
source}], nets: [{ref, signal_class, voltage_v, current_a, source}],
wires_hint: [{from, to, net}]}`. `python -m wire import --from
circuit-json <file>` validates it against `ConnectivitySource`, copies the
values into contract stubs, and records `{system: "circuit", ref,
sha256}` in `imported_sources`. The wire contract never links back — the
copy is the truth; re-import produces a diff, not live coupling. Generic
E3-style From/To CSV tables import through `--from csv` the same way.

### Inbound: envelope anchors (`*.envelope.json`, source `mech`)

Routes may declare `anchors[]` (clip, grommet, breakout seat names).
mechanical-agent can export `*.envelope.json` (`{anchors: [{name,
kind, position_mm}]}`) describing fixturing points in the product volume.
`python -m wire import --from mech-envelope <file>` validates the file and
records it in `imported_sources`; the `anchor_resolution` check verifies
every declared anchor exists in the imported envelope. Without an
envelope file the check reports `unknown` only when anchors are declared —
declared routing stays self-contained.

### Outbound: telemetry (source `bard`)

wire-agent emits standard workspace artifacts (contract, intake,
design-report.json/md, provenance.json) that bard-agent reads to compose
songs about the work. No wire-specific coupling exists; bard observes the
same files reviewers do.

### Outbound (v0.2+): fixtures to mech

Clip/grommet/fixture declarations in the contract can seed a mech design
brief (bracket/clip design). Deferred; the contract shape already carries
the data.

## Non-cooperation with acd-agent

Per product decision, wire-agent has no acd dependency: no import, no
Design Graph link, no HarnessContract reuse. Conceptually similar gates
are re-implemented against `src/wire` so the repository stands alone; if
both ecosystems are loaded in one conversation they share nothing but the
filesystem.

## Consequences

- Cooperation survives version skew: each side validates the JSON it
  reads and fails closed on unknown/missing fields.
- Imported data carries sha256 provenance, so gates can distinguish
  declared intent (R*/A*/Q*) from imported fact (I* sources).
- An E2E test in `tests/` exercises the CSV and JSON adapters with
  golden files; sibling repos are never fetched at test time.

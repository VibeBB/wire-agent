# ADR-0003: Plugin cooperation via contract files and task delegation

- Status: Accepted (revised 2026-09-23 after first multi-plugin
  verification)
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

Three boundary contracts, each a plain JSON file in the project directory.
The wire-agent importer models (`src/wire/imports.py`) are the schema
source of truth; both are versioned with `schema_version: 1` and a fixed
`system` tag.

### Inbound: connectivity (`*.connectivity.json`, source `circuit`)

electrical-circuit-agent exports a normalized connectivity view with
`circuit_connectivity_export` (MCP) / `python3 -m circuit.connectivity_export`
(CLI):

```
{schema_version: 1, system: "circuit",
 connectors: [{ref, family_hint?, housing?, rated_current_a,
               rated_voltage_v, cavities: [id...]}],
 nets: [{ref, signal_class, voltage_v, current_a}]}
```

`python -m wire import --from circuit-json <file>` validates it against
`ConnectivitySource`, copies the values into contract stubs, and records
`{system: "circuit", ref, sha256}` in `imported_sources`. The wire
contract never links back — the copy is the truth; re-import produces a
diff, not live coupling. Generic E3-style From/To CSV tables import
through `--from csv` the same way (`system: "csv"`).

### Inbound: envelope anchors (`*.envelope.json`, source `mech`)

Routes may declare `anchors[]` (clip, grommet, breakout seat names).
mechanical-agent exports `*.envelope.json` with `mech_export_envelope`
(MCP) / `python -m mech export-envelope` (CLI) from the brief's
`harness_anchors` declarations:

```
{schema_version: 1, system: "mech",
 anchors: [{name, kind: clip|grommet|breakout|other, position_mm?}]}
```

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

## Runtime boundary (revision)

Plugin package code runs inside each plugin's pinned tools image; the
per-plugin launcher (`plugins/<p>/scripts/<p>_launcher.py`) is the single
exec point for `hooks.json` and `.mcp.json`, and resolves the image in
order `$<PKG>_TOOLS_IMAGE` → digest lock (`tools-image.json` /
`docker/image-digests.json`) → error (revised: the earlier local-build
fallback was removed — docker and a resolvable pin are now required).
The resolved source tree is mounted read-only at
`/plugin-src`; the workspace is mounted at its own path so file paths are
identical inside and outside the container. Host Python is never the
plugin runtime — it only has to exec `docker`.

Contract fixtures live in `tests/fixtures/upstream/`; the emitter repos
keep golden copies pinned against the same payloads.

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
- Upstream emitters make the chain deterministic: neither side hand-writes
  the other side's contract files.
- Containerized runtimes remove host-dependency drift (build123d, libGL,
  pydantic/mcp versions) from the cooperation surface.
- Tests in `tests/` exercise the CSV and JSON adapters against the golden
  fixtures; sibling repos are never fetched at test time.

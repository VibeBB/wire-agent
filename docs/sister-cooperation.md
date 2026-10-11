# Sister cooperation

wire works with its sister plugins only through files in the shared
workspace and `task` delegation (ADR-0003). It never imports a sister
package.

## Inputs from sisters

| Sister | File | wire entry point | What wire takes |
| --- | --- | --- | --- |
| electrical-circuit | connectivity JSON (`system: circuit`) | `wire_import kind=circuit-json` | connectors, cavities, nets, signal classes, voltages, currents |
| any | CSV table | `wire_import kind=csv` | connector/cavity/net rows |
| mechanical | envelope JSON (`*.envelope.json`) | `wire_import kind=mech-envelope` | named anchors with kind and `position_mm` |
| UX-creator | `liaison/<id>.ux-request.json` | `wire_ux_inbox` | requested changes, deliverables, acceptance |

Each import is recorded as an `I*` imported source with the file's
sha256. Re-importing the same `(system, ref)` replaces the entry (new
hash, anchors and positions) and appends only connectors/nets with new
refs. The `import_freshness` gate fails when a recorded source changed
on disk after its import; `anchor_resolution` fails when a route names an
anchor no import declares; `route_geometry` fails when a route is shorter
than the straight-line path through its placed anchors; `route_keepout`
fails when that path enters a keep-out box from the envelope `keepouts`
(mech exports the board volume and brief-declared `harness_keepouts`, in
the anchor frame) and is `unknown` when the import carries no `keepouts`.

## Outputs to sisters

`out/<name>/` holds the wire list, cut table, BOM, diagram, route plan,
manifest and provenance. production-engineering, document and bard read
them as files; dashboard reads `design-report.json`.

## simulation-agent PDN handoff

wire's own `voltage_drop` gate checks one wire at a time at its nominal
resistance. A supply loop also drops voltage across series wires through
splices and across the return conductor, and copper resistance rises
with temperature. When the contract declares `simulation.rails[]`, wire
hands those loops to simulation-agent:

1. `wire sim-request` / `wire_sim_pdn_request` writes
   `<contract_id>.pdn.sim.json` (a simulation brief with one `pdn` rail per
   loop: every wire of the supply and return nets as a `wire` branch with
   its contract length and `resistance_ohm_per_km`, the net voltage, the
   net current at the load, the net drop limit — `max_voltage_drop_v`, or
   3 % of the net voltage — and the contract ambient) and
   `<contract_id>.pdn.sim-request.json` (`from_system: wire`, `kind: pdn`,
   request id `<contract_id>-pdn-<brief sha256[:12]>`). Ampacity stays
   with wire's derated `ampacity` gate and is not sent.
2. simulation-agent answers with `sim respond`, writing
   `<contract_id>.pdn.sim-response.json` beside the request.
3. The `sim_pdn` gate (and `wire sim-check` / `wire_sim_pdn_check`) reads
   `simulation.response_path`. A missing or malformed response,
   `needs_info` or `deferred` is `unknown`. A changed request file, a
   response to another requester or kind, a request id or brief sha256 the
   current contract would not emit (stale), a changed report or a
   report/response verdict mismatch is `fail`. Otherwise each simulation
   `pdn.*` check is reported with simulation's verdict, measured drop,
   limit, margin and guidance; a simulation `fail` or `unknown` is never
   promoted.

`response_path` is not part of the brief, so moving the response does not
change the request id. Editing a wire length, wire type, net voltage,
current or limit, or the ambient changes the brief and makes the old
response stale.

## production-engineering formboard handoff

`wire formboard` / `wire_formboard_export` writes
`<contract_id>.wire-formboard.json` (`artifact_kind: wire_formboard`,
`schema_version` 1, `contract_id`, `contract_sha256`): every route
flattened 1:1 with its total `length_mm`, `protection`, ordered `anchors`,
`segments[]` (`id`, `start_mm`, `end_mm`, `min_bend_radius_mm`) and the
`wires[]` laid on it (`id`, `net`, `cut_length_mm`, `slack_mm` = cut
length minus route length), plus `unrouted[]`, `short[]`, `unknown[]` and
`verdict`. The verdict is `fail` when a wire is shorter than its route
(the `route_fit` gate fails on the same data) or the contract declares no
route.

## production-engineering crimp handoff

`wire crimp` / `wire_crimp_export` writes `<contract_id>.wire-crimp.json`
(`artifact_kind: wire_crimp`, `schema_version` 1, `contract_id`,
`contract_sha256`, `conditions[]` — every `CrimpCondition` field plus the
sorted `ends[]` (`<wire>:a|b`) it crimps — `unknown[]` and `verdict`).
The verdict is `pass` only when the contract has a crimp table and every
connector termination resolves to a condition. production-engineering
imports it as `wire-crimp` and its `wire.crimp` gate requires a crimp
height and a pull force characteristic per condition, inspected on a
harness operation, with limits no looser than the table.

## Sister Liaison Protocol (SLP) v2

UX-creator directs the family. It writes one request per job; each
sister answers with one response. wire implements the responder side in
`src/wire/liaison.py`.

### Request (`liaison/<id>.ux-request.json`, written by UX-creator)

| Field | Type | Notes |
| --- | --- | --- |
| `schema_version` | `2` | |
| `system` | `"ux-creator"` | |
| `id` | slug | equals the file stem |
| `target_agent` | `bard`, `circuit`, `dashboard`, `doc`, `firmware`, `fpga`, `mech`, `prodeng`, `sim`, `wire` | wire reads only `wire` |
| `stage` | `requirements`, `design`, `manufacturing_handoff`, `build`, `evaluation`, `revision` | |
| `risk` | `low` or `high` | |
| `purpose` | text, 20+ characters | |
| `rationale` | text | |
| `requested_changes`, `expected_deliverables`, `acceptance` | non-empty lists | |
| `inputs` | `[{path, sha256}]` | hashed at request time |
| `depends_on` | request ids | |
| `created_at` | ISO 8601 | |

Unknown fields are rejected (strict models).

### Inbox states

| State | Meaning |
| --- | --- |
| `new` | no response yet |
| `answered` | response exists and nothing it relies on changed |
| `stale` | an input's sha256 differs from the request, or an input/artifact differs from the response |
| `blocked` | a `depends_on` request has no response yet |

Precedence is `stale`, then `answered`, then `blocked`, then `new`.
High-risk requests get a note when their `rationale` cites no job id
from the workspace `*.ux.json` contracts. Malformed request or response
files are listed with the validation error instead of being ignored.

### Response (`liaison/<id>.ux-response.json`, written by `wire_ux_respond`)

Input (`RespondInput`): `request`, `status` (`accepted`, `in_progress`,
`done`, `rejected`, `deferred`, `needs_info`), `reason`, `artifacts`
(paths), `design_reports` (paths whose checks become `gate_verdicts`),
`gate_verdicts`, `decision_refs`, `impression_refs`,
`questions_for_user`.

The writer adds `input_hashes`, hashed `artifacts`, `responder: wire`
and `responded_at`. Rules:

- every status except `accepted`/`in_progress` needs a reason of 20+
  characters; `needs_info` needs at least one question;
- `decision_refs`/`impression_refs` must be event ids present in the
  wire VRP logs;
- the request file must exist, match its stem and target `wire`; every
  artifact must exist;
- `done` needs gate verdicts (from `design_reports` or `gate_verdicts`)
  with none `fail`/`unknown`, at least one artifact and one impression
  reference, and a request that is neither stale nor has unanswered
  dependencies.

The response file is a protected projection: change it only by calling
the writer again.

## Change control (ECR/ECO)

A change to a file that another agent pins by sha256 goes through
UX-creator's change records, never a silent re-pin. There is no human
approval step.

1. Raise `<id>.ecr.json` with the reason, the proposal and each file to
   change with its current sha256.
2. After regenerating, write `<id>.eco.json` with each file's `before` and
   `after` sha256, the gate report that passed it (verdict `pass`, citing
   the `after` sha256) and the AI review findings with their dispositions.
   A `blocker` closes only as `fixed`, and the author cannot review its own
   change.
3. `ux change <eco>` (MCP `ux_change_check`) finds every consumer that pins
   a changed file. It fails if one still pins the old sha256, or re-pinned
   without being listed in the ECO.

AI review findings can only stop a change. This plugin's deterministic
gates and the change check decide. The record formats are in
[UX-creator-agent `docs/sister-cooperation.md`](https://github.com/VibeBB/UX-creator-agent/blob/main/docs/sister-cooperation.md#change-control-ecreco-and-design-review).

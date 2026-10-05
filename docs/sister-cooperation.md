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
than the straight-line path through its placed anchors.

## Outputs to sisters

`out/<name>/` holds the wire list, cut table, BOM, diagram, route plan,
manifest and provenance. production-engineering, document and bard read
them as files; dashboard reads `design-report.json`.

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

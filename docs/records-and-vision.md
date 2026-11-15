# Records and vision

wire implements the VibeBB Record Protocol (VRP) v2 described in
[records-protocol.md](records-protocol.md). This page lists what wire
records at each stage and where vision is used.

## Records per stage

| Stage | Decision examples | Stage impression covers | Vision reviews |
| --- | --- | --- | --- |
| `brief` | connector family, wire spec choice, assumption vs question for an image claim | contract + intake | each intake image (`intake_image`) |
| `design` | each contract repair for a failing gate (gauge up, route re-plan, segregation split) | `out/<name>/` tree | `harness-diagram.png` (`harness_diagram`), `route-plan.png` (`route_plan`) |
| `review` | whether a finding becomes a contract change | review records | every raster in `vision_points`, sister renders (`sister_artifact`), built harness photos (`built_harness_photo`) |
| `liaison` | accept, defer, reject or ask for info on a UX request | `liaison/<id>.ux-response.json` | images supplied with the request |

Logs live in `observations/wire/` (`decisions.jsonl`, `impressions.jsonl`,
`vision-reviews.jsonl`, `reads.jsonl`, `insights.jsonl`,
`reconciles.jsonl`, `song-receipts.jsonl`, `vision-tool-events.jsonl`,
`image-observations.jsonl`, `records-status.json`). Only the validated
writers may append; `protect-generated` blocks direct edits.

## Sister impressions

`python -m wire import` of a circuit `*.connectivity.json` or a mech
`*.envelope.json` logs an `upstream_read` with the producer impressions
bound to the imported bytes (or named in the file's `impression_refs`).
The import itself never fails on a missing impression; the read is
`unknown` instead. Until a later wire impression answers each one in
`upstream`, the Stop hook keeps asking. `wire_records_search` and
`wire_records_digest` read every sister's impressions; a sister log
with a broken chain is reported, never mixed into the results.

## Blind second review

`harness-diagram.png` and `route-plan.png` match `dual_review_globs`.
After the primary review, delegate one review to `wire-blind-review`,
whose `blind-guard` hook hides every earlier review, then reconcile with
`wire_record_reconcile`. A split allows one tiebreak and a second
reconcile; a split after that is unknown.

`python -m wire review-record --vrp-json <body.json>` writes the typed
advisory record and the VRP v2 vision review in one step; without
`--vrp-json` only the advisory record is written and the vision review
is reported as skipped.

## Thresholds

- Impression: at least 400 characters and three distinct sentences, two
  observations, one thing that works, a concern (or a reason for none),
  maker and user feelings, a next action and two grounded claims (one for
  a vision review, plus a lookback per claim).
- Decision: question of 10+ characters, principles of 12+ characters
  each, at least two options with pros and cons, a rationale of 200+
  characters, at least one evidence item and one risk, and a
  `revisit_when` observation.
- Typed advisory record (`review-visual-<slug>.advisory.json`): same
  impression floor; findings use the categories in
  [contracts.md](contracts.md#advisory-visual-review).

## Vision points

| Point | Image | How it reaches the model | Checklist |
| --- | --- | --- | --- |
| Intake | pinout photo, datasheet table, sketch | attachment → `intake/attachments/`, `wire_view_image` or `inspect_image_with_vision` | `intake_image` |
| Harness diagram | `harness-diagram.png` | inline from `wire_author` / `wire_drawio` | `harness_diagram` |
| Route plan | `route-plan.png` (only with placed mech anchors) | inline from `wire_author` | `route_plan` |
| Sister artifacts | mech drawing, circuit schematic, UX storyboard | `wire_view_image` | `sister_artifact` |
| Built harness | photo of the manufactured harness | attachment or `wire_view_image` | `built_harness_photo` |

`design-report.json` carries `vision_points` (path + checklist) for the
renders in the export directory, so the reviewer knows which rasters
need records. The `record-image-observation` hook logs every image the
model received (file editor views, `wire_author`, `wire_drawio`,
`wire_view_image`) and the Stop hook refuses to end the session until
each one has a vision review.

## What a vision impression should judge

Accuracy against the contract (every wire, cavity and route present and
correct), ambiguity a stranger could misread, whether the design intent
comes across (why this route, why this splice), usefulness to the maker
and to the end user, and the next step. Legibility alone is not enough.

Vision results and impressions are advisory (L2): they never change a
gate verdict, and they may only push toward more work, never toward a
pass.

## Known canon behaviour

The Stop-hook logic lives in the shared family canon
(`hooks/scripts/_records.py`, `require_records.py`) and is not changed
here. Observed behaviour worth knowing:

- `changed_artifacts` runs one `Path.glob` per artifact glob over the
  whole workspace and filters `.git`/`.venv`/`node_modules` only after
  the walk, so a large workspace is walked once per glob (12 times for
  wire) at every Stop.
- Change detection is mtime-based: regenerating a projection with
  identical bytes still counts as a change. It is then covered by any
  impression whose recorded sha256 still matches, so the cost is only
  an extra impression when none exists yet.
- An impression whose `artifacts` contains `.` covers every changed
  file while its tree hash matches, which is rarely true for a whole
  workspace; list concrete output directories instead.

## Session-scoped Stop status

The Stop hook excludes a record with an explicit different session ID,
even when its timestamp is recent. Legacy records without an ID are
eligible only from the session start through the following 24 hours;
their use is reported as an attribution warning. Missing session
identity or a missing start marker also leaves attribution unverified.
Reviews bind both the resolved image path and its SHA-256; an event ID
cannot substitute for that binding. Supply an explicit `image_path` to
the review writer so it records the current bytes. Legacy reference-only
reviews remain readable but do not discharge image-review obligations.

Stop writes `observations/<plugin>/records-status.json` and a
`observations/<plugin>/.sessions/<session>.status.json` snapshot:

| Field | Meaning |
| --- | --- |
| `stop_permission` | `deny` while the configured refusal budget remains, then `allow` |
| `record_compliance` | `fail` for missing evidence, `unknown` for attribution warnings, otherwise `pass` |
| `run_completion` | `unknown`; only the execution workflow can establish completion |
| `acceptance` | `unknown`; only the product acceptance workflow can establish it |
| `checkpoint` | Session marker containing the start time and refusal count |

An exhausted refusal budget permits termination while preserving the
unresolved problems. The compatibility `verdict` describes the hook's
problem list only; consumers must use the explicit fields above and must
not infer product acceptance from Stop permission or the absence of
record problems. Reviewer identity propagation and derived-image
ownership require a separate recording contract; this status does not
claim to verify them.

## Session attribution

Pass the native `session_id` from the SessionStart record context in record-tool
inputs. The writer also accepts `OPENHANDS_SESSION_ID` when supplied by the SDK
process; conflicting explicit and environment identities are rejected. The ID is
included in the record hash. Writers never infer it from shared marker files.

Delegated SessionStart hooks expose only native record context (`record-context`), without
recalling earlier review prose. Ordinary plugin SessionStart retains sister-concern recall.

Delegate independent reviews with an opaque `primary_event_id`, the resolved image
path and SHA-256; never send the earlier findings. Reviewers keep their own native
`session_id`. The writer and Stop resolve that reference into an intact primary
with the same plugin, path and hash and a different native session. Every review
role has its own session. Reconciliation belongs to the primary's session.

A copied image has its own round. Historical inputs without identity remain
supported, with bounded timestamp attribution and an unknown compliance warning
at Stop; they cannot satisfy explicitly scoped writer rounds.

Stop permission, record compliance, run completion and acceptance are separate
status fields. Reaching the refusal budget permits stopping while preserving gaps;
it does not establish execution completion or product acceptance.

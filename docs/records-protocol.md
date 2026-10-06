# VibeBB Record Protocol (VRP) v2

Every VibeBB plugin leaves the same kinds of records in the workspace, so
the reasoning behind a product survives the session that produced it and
every sister (and the UX producer) can read, cite and question it. The
impression is the core: a long-form reading of an artifact, tied to the
exact bytes it read, structured enough to be searched and answered, and
chained so that an edit, a deletion or a reordering is detected. This
file is the canonical specification; `wire-agent` holds the reference
implementation and the other plugins copy the shared hook files
(locked by `scripts/check_shared_hooks.py`).

## Logs

All logs are append-only JSONL under `observations/<plugin>/`
(`records_dir` in `plugins/<plugin>/hooks/records-policy.json`).

| File | Kind | Written when |
|---|---|---|
| `decisions.jsonl` | `decision` | every non-trivial design choice, without being asked |
| `impressions.jsonl` | `stage_impression` | at the end of every stage, after the final regeneration |
| `vision-reviews.jsonl` | `vision_review` | every time the model looks at an image (primary, blind or tiebreak) |
| `reads.jsonl` | `upstream_read` | a sister artifact was taken in; lists the sister impressions bound to it |
| `insights.jsonl` | `insight_status` | a hypothesis from an impression is tried, adopted, rejected, deferred or superseded |
| `reconciles.jsonl` | `review_reconcile` | independent vision reviews of one image were compared |
| `song-receipts.jsonl` | `song_receipt` | a bard song addressed to this plugin was read |
| `vision-tool-events.jsonl` | (hook) | `inspect_image_with_vision` answers |
| `image-observations.jsonl` | (hook) | images returned by plugin tools |
| `records-status.json` | (hook) | last Stop verdict, owed records and warnings |
| `.sessions/<session>.json` | (hook) | session start time and Stop refusal count |

A log written entirely by VRP v1 is renamed to `<name>.v1.jsonl` on the
first v2 write and stays as evidence; v1 and v2 lines never share a log.

## Envelope and hash chain

Every record carries `schema_version` (2), `kind`, `plugin`,
`sequence` (1-based line number), `prev_event_id` (the previous line's
`event_id`, 64 zeros on the first line), `recorded_at` (ISO-8601 with
timezone), `writer` (`plugin`, plus `agent` and `model` from
`VRP_AGENT`/`VRP_MODEL` when set) and `event_id`: the sha256 of the
canonical JSON (sorted keys, compact separators, UTF-8) of the record
without `event_id`.

`verify_log` fails closed on a malformed line, an `event_id` that does
not match the content, a broken `prev_event_id` link, a sequence gap or
reordering, a duplicate `event_id`, a `recorded_at` that goes back in
time, and any record that fails its kind validator. A writer refuses to
append to a log that fails verification (move it aside to start a new
chain), and readers treat the plugin's records as unknown: they are
reported under `integrity_problems`, never mixed into results, and a
reference into them does not resolve.

The chain proves the log was not edited, deleted from or reordered after
writing. It does not prove who wrote a line or that its content is true.

## Impression body

Shared by `stage_impression` and `vision_review`:

| Field | Rule |
|---|---|
| `impression` | 400+ characters, 3+ distinct sentences (`。！？` always end one; `.!?` only before whitespace or the end, so `3.3 V` does not) and at least one claim anchor quoted verbatim |
| `facets.observed` | 2+ concrete observations |
| `facets.works` | 1+ thing that works |
| `facets.concerns` | `{id, text, severity info/warning/error, about, anchor?}`; `about` names the plugin that owns it or `self`; empty only with `no_concerns_reason` (40+ characters) |
| `facets.feelings` | `maker` and `user` — how each would feel about the result |
| `facets.next_actions` | 1+ next step |
| `claims` | `{text, anchor, artifact}`; 2+ for a stage impression, 1+ for a vision review |
| `insights` | optional `{id, hypothesis, proposed_change, expected_effect, test, target, revisits?, revisit_reason?}` |
| `upstream` | optional `{system, event_id, disposition adopted/deferred/disputed/noted, effect, concern_ids?}` |
| `confidence` | `low`, `medium` or `high` |
| `unknowns` | list (empty only when truly none) |
| `delta` | required (40+ characters) when the prose is similar to an earlier one |

Write-time checks (writer only, they need the workspace):

- **Grounding**: each claim's `artifact` must be one of the bound
  artifacts (or inside a bound directory) and its `anchor` must occur in
  that file's text. Binary artifacts are grounded by the vision
  `lookback` instead.
- **Novelty**: character 5-gram Jaccard against this plugin's earlier
  impressions of the same kind; 0.80 or more is refused, 0.60 or more
  needs `delta`. Character n-grams work for Japanese and English alike.
- **Upstream resolution**: every `upstream` entry must resolve to an
  existing impression in an intact sister log; `concern_ids` must exist
  in it.
- **No concern ping-pong**: a concern a sister marked `disputed` cannot
  be raised again (same `about`, Jaccard 0.60 or more) while the bound
  artifact hashes are unchanged.
- **No rejected re-proposal**: a hypothesis 0.80 similar to a rejected
  insight is refused unless it names the old one in `revisits` with a
  `revisit_reason`.

## Other kinds

- `decision`: question, principles (each 12+ characters), 2+ options with
  pros and cons, `chosen` among them, rationale 200+ characters, evidence
  (paths are hashed; references cite standards or datasheets),
  assumptions, unknowns, 1+ risk, `revisit_when`, optional
  `impression_refs` that must resolve.
- `vision_review`: `image_path` + `image_sha256` or `source_event_id`,
  `model`, `checklist`, `reviewer` (`primary`, `blind`, `tiebreak`),
  findings, the impression body, and `lookback` with one
  `{claim, verdict confirmed/refuted/uncertain, note}` per claim — the
  model looks at the image again for each claim. A refuted claim must
  surface as a finding.
- `upstream_read`: `artifact` (path + sha256), `producer`, `refs`
  resolved from the artifact's `impression_refs` or from producer
  impressions bound to the same bytes, and `unresolved` problems.
- `insight_status`: `insight` (`system`, `event_id`, `insight_id`),
  `status`, `reason`, `evidence`, `gate_verdicts`, `decision_refs`,
  `revisit_when` for `deferred`. Transitions: proposed → tried / rejected
  / deferred; tried → tried / adopted / rejected / deferred; deferred →
  tried / rejected; adopted → superseded. `adopted` needs a
  deterministic gate `pass` and the adopting decision.
- `review_reconcile`: `image_sha256`, `reviews`, `round` (1 or 2),
  `outcome` (`agree`, `disagree`, `unresolved`) and `metrics`, computed
  deterministically by `reconcile()`.
- `song_receipt`: `delivery` (path + sha256 of the
  `liaison/<id>.bard-song.json`), `song_id`, `felt` (160+ characters,
  2+ sentences), `prompted_review` and `follow_up` when true.

## Blind review and reconciliation

Images matching `dual_review_globs` need a second review by a sub-agent
that cannot see the first: its `blind_guard.py` pre-tool hook denies
reads of `observations/`, advisory records, design reports, liaison
answers and songs, because a judge drifts toward any earlier verdict it
can see. Two reviews agree when their finding categories overlap by
Jaccard 0.5 or more and no `error` category is raised by only one side.
A `disagree` allows exactly one `tiebreak` review and a round-2
reconcile; it settles the split only by agreeing with one side, and a
split after that is `unresolved`, which counts as unknown and never as
pass. The writers refuse a second blind or tiebreak review per image and
a second reconcile per round.

## Bard songs

bard writes `liaison/<id>.bard-song.json` (`kind: bard_song_delivery`,
`to`, `title`, `verse`, `song` path + sha256, `impression_refs` it was
made from, `reason`, `created_at`). The addressed sister records a
`song_receipt`. A receipt never asks bard for anything: bard does not
compose in reply to receipts. Songs are advisory and never a gate input.

## Loop and deadlock bounds

- Stop refuses at most `max_stop_denials` times (default 2) per session,
  then allows with the gaps in `records-status.json`.
- Records cite only records that already exist; nothing waits for a
  future record, so two plugins cannot wait on each other.
- A disputed concern returns only with new artifact bytes; a rejected
  hypothesis only with `revisits` and a reason.
- One blind review, at most one tiebreak, at most two reconcile rounds.
- A song receipt and a read receipt never require a new impression from
  the producer.
- Hook errors never block; a broken log makes references unknown, not a
  permanent refusal loop (the Stop limit still applies).

## Enforcement

`hooks/scripts/require_records.py` runs on `session_start` (session
marker, plus a recall briefing of sister concerns about this plugin,
unanswered reads and waiting songs) and first on `stop`. At Stop it lists
everything this session owes:

- every integrity problem in this plugin's logs;
- a vision tool event or viewed image without a bound `vision_review`;
- a sister impression read this session that no later impression cites
  in `upstream`;
- a primary review of a dual-review image without a blind review, a
  reconcile, or the single allowed tiebreak;
- a bard song addressed to this plugin without a receipt;
- a changed artifact without a fresh `stage_impression` (its recorded
  sha256 equals the current file or tree), and changed artifacts without
  a `decision`.

If anything is owed the hook exits 2 with
`{"decision": "deny", "reason", "additionalContext"}`. Records are
advisory evidence (L2): they never change a deterministic gate verdict.

## Reading across plugins

- `digest(root)`: per-plugin integrity, counts and chain heads; open,
  deferred and disputed concerns sorted by severity; disputes;
  unacknowledged reads; insights with their current status; review
  splits; song deliveries and whether they were received.
- `search(root, query, system, kind, stage, artifact, severity,
  open_only, limit)`: keyword search over every intact plugin's
  impressions.
- `recall(root, plugin)`: the SessionStart briefing.

## Writers

- MCP: `<plugin>_record_decision`, `_record_impression`,
  `_record_vision_review`, `_record_reconcile`, `_record_read`,
  `_record_insight`, `_record_song_receipt`, `_records_status`,
  `_records_digest`, `_records_search`. Input schemas are the Pydantic
  models in `src/<package>/records.py`.
- CLI: `python -m <package> record
  decision|impression|vision-review|reconcile|insight|song-receipt|read
  --json <file>` and `record status|digest|search`.
- `src/<package>/_vrp.py` is a byte copy of `hooks/scripts/_records.py`,
  so the writer and the Stop hook share one validator and one hash
  function; a test pins the copy.
- `protect_generated.py` blocks direct edits to every log and to song
  deliveries.

## Porting checklist (per plugin)

1. Copy `hooks/scripts/_records.py` and `require_records.py` unchanged
   and update `EXPECTED` in `scripts/check_shared_hooks.py`; copy
   `_records.py` to `src/<package>/_vrp.py`.
2. Set `schema_version: 2` and `dual_review_globs` in
   `hooks/records-policy.json`.
3. Port `src/wire/records.py` (change `PLUGIN` only), the ten MCP tools
   and the `record` CLI kinds.
4. Add `blind_guard.py` and a blind review agent that declares it.
5. Update "Records you must leave" in every agent and the workflow skill,
   and the log names in `protect_generated.py`.
6. Port `tests/test_records.py`, including the chain, grounding,
   novelty, ping-pong, rejected-insight, finite-review and song tests.

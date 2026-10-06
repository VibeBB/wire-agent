# ADR-0011: VRP v2 — impressions as chained, grounded, answerable records

## Status

Accepted

## Context

VRP v1 made impressions mandatory but left them as free prose. Nothing
tied a sentence to the artifact it described, a near copy of the last
impression passed, a sister could not answer one, an edited log looked
the same as an honest one, and a second vision review would be anchored
by the first. The family treats impressions as a core technology: the
design rationale every sister, UX and bard read. Loops between sisters
(concern ping-pong, re-proposed hypotheses, review rounds, songs that
trigger songs) had to be impossible by construction.

## Decision

- Every v2 record carries `sequence`, `prev_event_id`, `writer` and an
  `event_id` over the canonical record; `verify_log` fails closed on any
  break, writers refuse to extend a broken log and readers report it as
  unknown.
- The impression keeps its prose and adds `facets`, grounded `claims`,
  `insights`, `upstream` answers, `confidence` and `unknowns`. Claim
  anchors must occur in the cited artifact text; near copies are refused
  or need `delta`.
- New kinds: `upstream_read`, `insight_status`, `review_reconcile`,
  `song_receipt`. Imports log read receipts; Stop asks until each sister
  impression is answered.
- Important renders get a blind second review by `wire-blind-review`,
  isolated by the `blind_guard.py` pre-tool hook, then a deterministic
  reconcile with at most one tiebreak.
- `src/wire/_vrp.py` is a byte copy of the hook validator so writer and
  hook cannot drift.
- Bounds: two Stop refusals, cite only existing records, no disputed
  concern without new artifact bytes, no rejected hypothesis without
  `revisits`, receipts never trigger new work for the producer.

## Consequences

- v1 logs are archived as `*.v1.jsonl` on the first v2 write.
- Impressions take more effort to write; the structure is what lets UX
  aggregate them and bard sing from them.
- The chain detects tampering but does not authenticate the writer.
- Vision, impressions and songs stay advisory (L2); no gate reads them.

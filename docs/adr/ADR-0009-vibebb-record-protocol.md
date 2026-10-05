# ADR-0009: VibeBB Record Protocol — mandatory decisions, stage impressions and vision reviews

## Status

Accepted

## Context

Only the circuit, mechanical, wire and bard plugins required an
impression on a vision review (240 characters, 2 sentences), and only as
an optional advisory file. No plugin recorded why a design choice was
made in a machine-checkable form, none asked for an impression at the end
of a stage, and the Stop hooks only printed status. A user who never asked
for records got none, and the UX producer had no common shape to read
across siblings.

## Decision

Adopt the VibeBB Record Protocol (`docs/records-protocol.md`) in every
plugin, with wire as the reference implementation:

- typed writers in `src/wire/records.py`, exposed as MCP tools and a
  `record` CLI subcommand, that hash every cited artifact and image;
- a stdlib validator `_records.py` and a Stop hook `require_records.py`,
  shared byte-for-byte across plugins, that refuse to finish a session
  that owes records (bounded by `max_stop_denials`);
- impressions raised to 400 characters and 3 distinct sentences; the
  existing `review-record` advisory uses the same rule and mirrors itself
  into `vision-reviews.jsonl`.

## Consequences

- Records are produced without user instructions; refusals are visible
  to the agent as Stop feedback and to everyone in `records-status.json`.
- Compatibility with the 240-character advisory floor is dropped.
- Records stay advisory: gate verdicts are unchanged.
- A model that cannot comply still terminates after the refusal limit,
  and the gaps are reported rather than hidden.

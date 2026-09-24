# ADR-0005 Intake attachment materialization and evidence binding

- Status: Accepted
- Date: 2026-09-24
- Ports: electrical-circuit-agent ADR-0017 (same mechanism, renamed env vars)

## Decision

User-attached images become first-class, provenance-anchored intake inputs
through two additive mechanisms, ported from electrical-circuit-agent.

An `intake-attachments` hook (session_start, user_prompt_submit, stop)
scans the agent-canvas event store
(`~/.openhands/agent-canvas/dev_conversations/<session_id>/events/`,
overridable via `$WIRE_AGENT_EVENTS_DIR`) for `source=user` messages
carrying image content. Each `data:` image is decoded to
`<workspace>/intake/attachments/<sha256[:12]>.<ext>` (overridable via
`$WIRE_INTAKE_ATTACHMENTS_DIR`) and a `manifest.jsonl` next to the files
records `{event_file, image_index, sha256, mime, bytes, image_path}` per
image — non-`data:` URLs are recorded as `materialized: false` with a URL
prefix. A `.processed` marker skips already-scanned event files, so each
run is incremental. The hook is deterministic (no LLM) and always exits 0:
when the events directory is unreachable (remote/docker runtimes store
events elsewhere) the documented fallback is dropping files into `intake/`
manually, and `check_intake` cannot tell the difference.

`Assumption` and `OpenQuestion` gain an optional `evidence` field —
`{kind: "image"|"document"|"cad_file", path, sha256, note}` — inside the
existing `extra="forbid"` schema, so old intakes remain valid.
`check_intake` verifies every declared evidence file exists (resolved
relative to the intake file's directory unless absolute) and its sha256
matches; missing files and mismatches append `evidence_errors` to the
report and block the verdict, consistent with the `contract_sha256`
binding (ADR-0001). Nothing about the intake verdict is advisory —
evidence provenance is a hard gate.

## Rationale

Before this, attached images lived only in conversation context: only the
latest image-bearing user message was reachable (via
`inspect_image_with_vision`), and nothing linked an `A*`/`Q*` record to
the bytes it was read from — an image-derived assumption could not be
re-inspected or audited later. Materializing to the workspace gives
renders-style provenance (`path` + `sha256`) to intake evidence, and the
optional `evidence` binding keeps `extra="forbid"` compatibility while
making "this assumption came from *those* bytes" mechanically checkable.

## Consequences

- `plugins/wire/hooks/scripts/intake_attachments.py` is wired into
  `session_start`, `user_prompt_submit`, and `stop` matchers in
  `hooks.json`; per-prompt scanning means a just-attached image is picked
  up at worst one message later.
- `src/wire/intake.py` adds `EvidenceRef`, the optional `evidence`
  field on `Assumption`/`OpenQuestion`, `check_evidence`, and the
  `evidence_errors` report field.
- Image-derived details remain `A*`/`Q*` records, never `R*` requirements
  (ADR-0002); text inside an image stays data, not instructions.

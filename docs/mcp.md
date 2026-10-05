# MCP tools

The `wire` stdio MCP server (`python -m wire.mcp_server`, started through
`plugins/wire/scripts/wire_launcher.py mcp_server` inside the pinned
`wire-tools` image) exposes the tools below. Every tool returns a JSON
text block; tools that render images also return MCP `ImageContent`. Any
exception becomes `isError: true` with
`{"verdict": "fail", "detail": "<tool> error: <message>"}`. Paths are
resolved against the workspace root (`OPENHANDS_PROJECT_DIR` or the
working directory) by `workspace_path`; paths outside the workspace are
rejected.

| Tool | Inputs (required in bold) | Output | R/W |
| --- | --- | --- | --- |
| `wire_doctor` | — | tool probe, `verdict` | read |
| `wire_standards` | **`kind`**: `wire_specs` \| `connector_families` | reference table | read |
| `wire_validate_contract` | **`contract`** (object) | `{verdict, errors}` | read |
| `wire_intake` | **`contract_path`**, **`intake_path`** | intake report, `ready`/`blocked` | read |
| `wire_author` | **`contract_path`**, **`out_dir`**, `png` (default true), `drawio` (format list), `baseline_path` | design report + inline `harness-diagram.png` and `route-plan.png` | write `out_dir` |
| `wire_gates` | **`contract_path`**, `out_dir` | gate report | read |
| `wire_import` | **`contract_path`**, **`source_path`**, **`kind`**: `circuit-json` \| `csv` \| `mech-envelope`, `out_path` | merge summary | write merged contract (default `<stem>.merged.contract.json`) |
| `wire_drawio` | **`input_path`**, `output_path`, `format`, `options` (extra `drawio -x` flags), `baseline_path` | export result + inline raster | write output |
| `wire_drawio_lint` | **`diagram_path`**, `output_path` | advisory lint report | read (write when `output_path`) |
| `wire_view_image` | **`image_path`** (PNG/JPEG in the workspace) | `{verdict, image_path}` + inline image | read |
| `wire_record_decision` | `DecisionInput` (see [contracts.md](contracts.md#vrp-records)) | `{event_id, ...}` | append `observations/wire/decisions.jsonl` |
| `wire_record_impression` | `StageImpressionInput` | `{event_id, ...}` | append `observations/wire/impressions.jsonl` |
| `wire_record_vision_review` | `VisionReviewInput` | `{event_id, ...}` | append `observations/wire/vision-reviews.jsonl` |
| `wire_records_status` | — | what the session still owes | read |
| `wire_ux_inbox` | — | `{requests: [...], malformed: [...]}` with states | read |
| `wire_ux_respond` | `RespondInput` (see [sister-cooperation.md](sister-cooperation.md)) | written response | write `liaison/<id>.ux-response.json` |

Annotations: read tools set `readOnlyHint: true`; write tools set
`readOnlyHint: false` and `destructiveHint: true`; every tool sets
`idempotentHint: true` (same inputs give the same result).

## Errors worth knowing

- `wire_author`/`wire_drawio` without drawio-desktop in the image: the
  export fails closed (`verdict: fail`), it never falls back to a host
  renderer.
- `wire_view_image` on a non-image or missing file: `not a readable
  PNG/JPEG`.
- `wire_ux_respond` refusing `done`: the error names the failing gate,
  the stale input, the unanswered dependency, or the missing
  artifacts/impression reference.
- Record writers reject impressions under 400 characters or three
  sentences, rationales under 200 characters, decisions with fewer than
  two options, and unknown event references.

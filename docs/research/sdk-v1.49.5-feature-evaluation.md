# Research note: OpenHands SDK v1.49.5 feature evaluation for wire

Checked on: 2026-09-23 (PyPI openhands-sdk 1.49.5, released 2026-09-23;
openhands-tools 1.49.5)

## Scope

wire consumes the SDK only as a plugin boundary (`plugins/wire`) plus the
`sdk-check` dependency group used by the `plugin-load` CI job. Features
that require runtime code (conversation orchestration, workspace
management, settings) are out of scope by design — the plugin declares
behavior, the host app executes it. The `wire` MCP server is a stdio
boundary over the deterministic `python -m wire` entry points.

## v1.49.4 → v1.49.5 delta

| Change | wire relevance |
| --- | --- |
| `openhands/sdk/utils/masking.py` — `PreserveDataUrls` / `SkipSecretMasking` context managers | positive — image `data:` URLs are no longer secret-masked; wire's PNG/SVG projections stay intact if a vision-capable model receives them via `inspect_image_with_vision` |
| `message.py` `image_urls` gains `PreserveDataUrls` | positive — same as above, on the message construction path |
| `mcp/tool.py` normalizes mcp 2.x snake_case ↔ camelCase wire keys | none now — `mcp` stays on 1.30.0 (`fastmcp<4` → `mcp<2.0`); the normalization is forward-compat for when the cap lifts |
| `openhands-tools` `browser_use` `screenshot_data` gets `SkipSecretMasking` | none — wire declares no browser tooling |
| `model_features.py` adds `gpt-6` family and `gpt-5.2-codex` | none — agents use `model: inherit` |
| `telemetry.py` adds `UsageSnapshot` | none — runtime surface, not plugin boundary |
| extensions metadata utf-8 fix | none — no extension assets |

## Evaluated features

| Feature | Decision | Rationale |
| --- | --- | --- |
| MCP `ToolAnnotations` (`title`, `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`) | **adopted** | Every `wire_*` tool now declares honest read/write hints so MCP clients (AgentCanvas and other hosts) can rank and gate calls. `wire_author`/`wire_drawio` are the only write tools; `wire_import` writes only a temp buffer server-side, so it is read-only on the MCP surface. |
| MCP tool `outputSchema` / `structuredContent` | not adopted | All tools return a single `TextContent` JSON envelope; adding a typed output schema duplicates the per-tool contracts already documented in the input schemas and docs. Deferred until a client requires it. |
| Vision path (`inspect_image_with_vision`, `file_editor` view) | already adopted | `wire-review`/`wire-brief` document the delegation pattern for non-vision primary models; `author --png` emits the 2× raster they inspect. Vision stays L2-only. |
| `paths:` (PathTrigger) skill rules | already adopted | `wire-contract-rules` fires on `*.contract.json`/`*.intake.json` touch; keyword skills remain model-invocable. |
| `prompt`/`agent` hook types | not adopted | Hook types other than `command` inject non-deterministic text/agent loops; the deterministic/fail-closed invariant keeps hooks stdlib `command` only. |
| `SessionEnd`/`Stop` extra events, `UserPromptSubmit` | not adopted | Current `session_start` + `pre_tool_use` + `stop` coverage matches the doctor/guard/status-report design; no new automation surface needed. |
| AgentCanvas | no action | `@openhands/agent-canvas` connects over ACP and installs plugins under `~/.openhands/plugins/installed/` — already covered by the plugin-root resolution order. Tool annotations improve how the canvas displays `wire_*` tools. |
| plugin.json `$schema` | not adopted | The 1.0.0 plugin schema field is tolerated-but-unenforced by the SDK loader (`extra="allow"`); adding it is cosmetic. Revisit when the loader starts validating. |

## Verification record

- `uv run python scripts/verify_all.py --stage fast`: pass (93 tests,
  1 skipped) — includes the new `tests/test_mcp_server.py` annotation
  assertions.
- `uv run --group sdk-check python scripts/check_plugin_load.py`: OK —
  SDK v1.49.5 loads the plugin unchanged.
- `uv run python scripts/check_dependency_updates.py`: clean except the
  recorded `mcp 2.x` deferral.

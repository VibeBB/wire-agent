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

## Named SDK feature review (2026-09-24)

Focused pass on the SDK's security / confirmation / secrets / stuck /
memory / model-routing surfaces. Sources: installed `openhands-sdk` and
`openhands-tools` 1.49.5 plus upstream `main` (`sdk/subagent/schema.py`,
`sdk/subagent/registry.py`, `sdk/conversation/impl/local_conversation.py`,
`sdk/conversation/secret_registry.py`, `sdk/security/`,
`sdk/llm/llm_profile_store.py`, `tools/task/manager.py`), and the
agent-server `conversation_service.py` / `conversation_router.py` on `main`.

| Feature | Where it lives | Decision | Rationale |
| --- | --- | --- | --- |
| `EnsembleSecurityAnalyzer` (`PatternSecurityAnalyzer` + `PolicyRailSecurityAnalyzer`, worst-case fusion) | `Conversation.state` / agent-server `POST /conversations/{id}/security_analyzer` | not adoptable at plugin boundary | `AgentDefinition` has no `security_analyzer` field; only the host app can attach an analyzer. Plugin-side substitute adopted instead: the `safety-rail` `pre_tool_use` hook denies a deterministic denylist on terminal commands. |
| `LLMSecurityAnalyzer` / `ToolShieldLLMSecurityAnalyzer` / `GraySwanAnalyzer` | same | not adoptable at plugin boundary | Same as above; all opt-in server-side analyzers. |
| `ConfirmRisky` (`permission_mode: confirm_risky`) | AgentDefinition frontmatter → conversation confirmation policy | **switched to `never_confirm`** | Finding A below: task sub-agent conversations never receive the parent's analyzer, so every action is `UNKNOWN` and `confirm_risky` auto-resumes — zero gating plus status churn. All wire sub-agents now declare `never_confirm` to match the real behavior; revisit if the SDK propagates the analyzer. |
| `SecretRegistry` (`/secrets` API, env injection) | conversation state; `${VAR}` expansion in `.mcp.json` / `mcp_config` | adopt (documentation only) | `${VAR}`/`${VAR:-default}` in `mcp_config` resolves through `secret_registry.get_secret_value` before env; `wire_launcher.py` already forwards `OPENHANDS_*`/`WIRE_*` env into the tools container, so a Canvas-registered `WIRE_*` secret reaches `wire_*` tool code end-to-end today. Remaining work is documenting the naming contract. |
| `StuckDetector` | `Conversation(stuck_detection=True)` default | already effective | On by default in every `LocalConversation`, including task sub-agents. Thresholds are Conversation init params — not plugin-settable; `max_iteration_per_run` already bounds runs. |
| Persistent memory (`AgentContext(load_memory=True)`) | server-side `AgentContext` (Canvas "Settings > Agent Context") | not adoptable at plugin boundary | The sub-agent factory builds `AgentContext` without `load_memory`; frontmatter has no switch. Top-level conversation only. |
| Model routing (`Router`/`MultimodalRouter`, `model:` frontmatter) | `Agent.llm` (server) / `LLMProfileStore` | **adopted via profile convention** | The Router itself is server-side. Authoring sub-agents now declare `model: vibebb-author`, reviews `vibebb-review` — operators create the matching profiles in `~/.openhands/profiles/` (contract in `docs/operations.md`); a missing profile hard-fails the spawn (Finding B). Custom `profile_store_dir` stays discouraged (it splits provider-connections resolution). |
| `SwitchLLMTool` / agent profiles (`mcp_server_refs`, `secret_refs`) / critic | agent-server profile + Canvas settings | not adoptable at plugin boundary | Server-side scoping features; wire-review already plays the critic role at L2. |
| `condenser:` frontmatter | AgentDefinition | not adopted | Sub-agents already get a summarizing condenser by default at factory time (`default_condenser`), so there is nothing to add; tuning `max_size`/`keep_first` stays an option for long review runs if pressure shows. |

### Persistent memory seed — `.openhands/memory/MEMORY.md`

`AgentContext(load_memory=True)` loads `<workspace>/.openhands/memory/MEMORY.md`
(project tier) plus `~/.openhands/memory/MEMORY.md` (user tier) into a
~6000-char prompt section. The seed committed at repo root ships the durable
invariants (gate authority, projection rule, fail-closed, secret flow,
profile names) for hosts that enable Canvas "Settings > Agent Context"; the
agent then maintains the index itself. Sub-agents cannot opt in — the factory
builds `AgentContext` without `load_memory` — so the seed serves the
top-level conversation only.

### Finding A — `confirm_risky` is effectively auto-approved in sub-agents

`openhands-tools` `task/manager.py` (verified on 1.49.5 and upstream `main`)
builds the child `LocalConversation` and calls `_set_confirmation_policy`,
but never calls `set_security_analyzer` — `state.security_analyzer` stays
`None`. Every action therefore carries risk `UNKNOWN`;
`ConfirmRisky` defaults to `confirm_unknown=True`, which raises
`WAITING_FOR_CONFIRMATION` per action and is then auto-approved because the
task path wires no confirmation handler. Net effect: zero gating plus
status-transition noise. Real gating needs an upstream propagation patch;
recorded here to drive the `permission_mode` policy decision.

### Finding B — `model:` fails hard when the profile is missing

`agent_definition_to_factory` calls `LLMProfileStore(base_dir).load(name)`
and raises `ValueError` for unknown names, killing the `task` call. Any
non-`inherit` `model:` must ship with a documented profile-name convention
(e.g. `~/.openhands/profiles/vibebb-strong.json`) that the operator creates
first.

### Finding C — the secret contract already works end-to-end

`SecretRegistry.get_secrets_as_env_vars` injects env vars into bash commands
that name the key, and `expand_mcp_servers` resolves `${VAR}` in
`.mcp.json` through the same registry. `wire_launcher.py` forwards
`OPENHANDS_*` and `WIRE_*` env into the tools container, so a
Canvas-registered `WIRE_*` secret reaches `wire_*` tool code inside the
container with zero plugin changes. Documenting the contract is the only
remaining work.

## Verification record

- `uv run python scripts/verify_all.py --stage fast`: pass (93 tests,
  1 skipped) — includes the new `tests/test_mcp_server.py` annotation
  assertions.
- `uv run --group sdk-check python scripts/check_plugin_load.py`: OK —
  SDK v1.49.5 loads the plugin unchanged.
- `uv run python scripts/check_dependency_updates.py`: clean except the
  recorded `mcp 2.x` deferral.

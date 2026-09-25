# Research note: OpenHands SDK v1.49.6 feature evaluation for wire

Checked on: 2026-09-25 (PyPI openhands-sdk 1.49.6, released 2026-09-25;
openhands-tools 1.49.6; agent-canvas 1.24.0 carrying automation 1.15.1)

## Scope

wire consumes the SDK only as a plugin boundary (`plugins/wire`) plus the
`sdk-check` dependency group used by the `plugin-load` CI job. Features
that require runtime code (conversation orchestration, workspace
management, settings) are out of scope by design — the plugin declares
behavior, the host app executes it. The `wire` MCP server is a stdio
boundary over the deterministic `python -m wire` entry points.

## v1.49.5 → v1.49.6 delta

| Change | wire relevance |
| --- | --- |
| Meta-profile routing: `llm/meta_profile_store.py`, `tool/builtins/classify_and_switch_llm.py`, agent-server `meta_profiles_router.py`, example `59_route_task_to_model.py` | operator-level — a meta-profile maps task classes to saved LLM profiles; it can point classes at the existing `vibebb-*` profiles |
| `verified_models.py`: adds `gpt-6-sol`, `gpt-6-luna`, `claude-opus-5-5`; drops `claude-opus-4-8` | none for the plugin — sub-agents resolve named profiles, never raw model strings. An operator profile still pointing at `claude-opus-4-8` is now "unverified" and Canvas 1.24.0 warns about it |
| `hooks/executor.py`: a non-string `decision` in hook JSON is treated as no decision | positive — hardens the `command` hooks (safety-rail, protect-generated, vision records) against malformed output |
| `llm.py`: friendly error on an invalid API key; refresh the key and retry once on a 401 | positive — runtime resilience, no repo change |
| `mcp/oauth.py`, `mcp/utils.py`, agent-server `mcp_oauth_store.py`/`mcp_router.py`: OAuth token refresh fixes | none now — `wire` MCP is stdio with no OAuth; it matters if an operator adds an OAuth MCP server |
| agent-server Windows crash fix | n/a — the verification host is Linux |
| docs: system-before-user LLM message invariant | none — documentation only |

## Evaluated features

| Feature | Decision | Rationale |
| --- | --- | --- |
| Meta-profile routing (`ClassifyAndSwitchLLMTool`, `MetaProfileStore`, `meta_profiles_router`) | not adoptable at plugin boundary | Routing is a conversation-level builtin plus operator config under `~/.openhands/meta-profiles/` (or `$OH_PERSISTENCE_DIR/meta-profiles`); AgentDefinition frontmatter cannot pin a meta-profile per sub-agent. An operator may define a meta-profile whose classes resolve to `vibebb-author`/`vibebb-review`; a classifier miss fails loudly, which matches fail-closed expectations. No repo change. |
| New verified models (`gpt-6-sol`, `gpt-6-luna`, `claude-opus-5-5`) | no action | Model choice lives in operator-side `~/.openhands/profiles/`; the plugin pins no model names. |
| Non-string hook `decision` hardening | inherent | All wire hooks emit `decision` as a string; malformed JSON no longer crashes the decision parse — it simply records no decision. |
| LLM 401 refresh-and-retry / friendly invalid-key error | inherent | No repo change. |
| MCP OAuth token refresh | inherent | No repo change. |
| AgentCanvas 1.23.0 → 1.24.0 (verification host) | host updated | The canvas now calls the agent-server runtime directly instead of `/api/cloud-proxy` (fixes 405 on verification confirm and compact-context), keeps MCP OAuth credentials on saves, and skips consent when tokens still work. Runtime-surface features (workspace-folder toggle, cloud read-only shared conversations) do not touch the plugin boundary. |

## DrawIO 31.4.5 → 31.5.2 (wire-tools image)

| Change | Decision | Rationale |
| --- | --- | --- |
| `--timeout` CLI flag (fails an export exceeding N seconds, continues with the next file) | **adopted** | Every `drawio -x` invocation in `src/wire/export.py` now passes `--timeout 300`, and the subprocess gains a matching outer bound (`timeout=420`). A hung export or a stuck Electron boot now ends as `RuntimeError` instead of blocking the run — fail-closed. |
| CLI exports fail with exit 1 instead of hanging on a dialog (invalid Mermaid, unknown/invalid `--layout`, crashed export or Visio import, unreadable file); empty Mermaid/CSV refused for HTML export | inherent | Removes the main headless-hang class; strengthens fail-closed with no code change. |
| `--normalize` CLI flag (repairs generated diagrams: mis-parented edges, edges without geometry, containers clipping children) | not adopted into the render path | Auto-repair would mask defects the generator or `drawio-lint` should surface. It stays reachable for user-supplied inputs through the `wire drawio` options passthrough. |
| Local-path shape libraries accepted again ("Path not authorized" regression since 31.4.4) | n/a | wire declares no custom library configuration. |
| Symlink protections on folder export/output/backup writes (GHSA-2w35-fgjm-2vvh, GHSA-36x5-vw5q-29rv) and full-path system-program launches (GHSA-qg46-52fx-h7p8) | inherent | Security hardening on the export path. |
| File-watch/save-conflict notices, Windows program-path fix, update-check suppression | n/a | Headless export path is unaffected; `--disable-update` was already passed. |

## Verification record

- `uv run python scripts/check_dependency_updates.py`: clean — no update
  candidates; only the recorded `mcp 2.x` and Python-3.14 deferrals remain.
- `uv run python scripts/verify_all.py --stage fast`: pass, including the
  updated `tests/test_dependency_check.py` pin assertions.
- Host AgentCanvas verified after the 1.24.0 update: `/ready`, `/health`,
  `/server_info`, `/api/automation/docs`, and `/canvas` all return 200, with
  agent-server/SDK/tools/workspace at 1.49.6.

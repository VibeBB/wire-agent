# OpenHands SDK v1.50.1 feature evaluation (wire-agent)

Scope: `openhands-sdk`, `openhands-tools`, and any directly pinned OpenHands packages move from 1.50.0 to 1.50.1 (PyPI upload 2026-09-30T19:31Z). The complete 16-commit upstream range `v1.50.0..v1.50.1` was reviewed. uv remains pinned at 0.12.21.

Primary source: [OpenHands SDK v1.50.1 release](https://github.com/OpenHands/software-agent-sdk/releases/tag/v1.50.1).

## SDK 1.50.0 -> 1.50.1

| Upstream change | Decision | Evaluation |
| --- | --- | --- |
| #5000 hard per-attempt timeout for async LLM streams | adopted implicitly | VibeBB profiles do not set `LLM.timeout`, so the 300-second hard timeout and `LLM.stream_idle_timeout` default apply. Both timeouts are retryable and map to `LLMTimeoutError`; no profile or shared-hook change is needed. `vision_is_active()` and the capability probe remain unchanged. |
| #5297 `openhands-tools` accepts non-UTF-8 text in `file_editor` | adopted with the pin | Useful for Japanese Shift_JIS/CP932 and other non-UTF-8 text inputs; no plugin code change is needed. |
| #5295 httpx[socks] >= 0.28.1; #5391 PyJWT 2.14.0 security fixes | lock-only | Refresh the requested SDK/tools lock resolution; these dependencies are picked up through `uv.lock` where they are present. |
| #5069 restore tool registrations after remote attach | not adopted | Plugins run in local conversations and do not use remote attach. |
| #5272 authenticated Canvas App backend bridge | not adopted | No VibeBB plugin ships a Canvas extension backend. |
| #5302, #5301, #5305 TypeScript client dependencies | not applicable | This repository does not use the SDK TypeScript client. |
| #5296 google-cloud-aiplatform 2.1.3 Vertex extra | not adopted | No VibeBB plugin enables the optional Vertex SDK extra. |
| #5378 agent-server budget-denial test | not applicable | Upstream test-only change; no repository behavior to adopt. |
| #5350 HTTP 429 admission control; #5369 idle-runtime catalog refresh; #5282 VSCode token on `/api/init`; #5393 git repository search | upstream image | Wire does not build or manage an OpenHands agent-server image; these changes do not require a plugin change. |
| #5410 release | not applicable | Release housekeeping; no plugin-level change. |

## Compatibility deferrals

MCP 2.x remains deferred because the installed SDK metadata still requires `fastmcp>=3.2.0,<4`, which constrains `mcp<2`. See `scripts/dependency_update_deferrals.json`.

## Lock scope

`uv.lock` was refreshed with `uv lock --upgrade-package openhands-sdk --upgrade-package openhands-tools`. The only package version changes are `openhands-sdk` and `openhands-tools`; `uv` remains `0.12.21`.

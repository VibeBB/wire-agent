# OpenHands SDK v1.51.0 feature evaluation (wire-agent)

Scope: `openhands-sdk` and `openhands-tools` move from 1.50.1 to 1.51.0
(PyPI upload 2026-10-03T07:38Z), and uv moves from 0.12.21 to 0.12.22. The
complete upstream range `v1.50.1..v1.51.0` was reviewed.

Primary sources: [OpenHands SDK v1.51.0
release](https://github.com/OpenHands/software-agent-sdk/releases/tag/v1.51.0),
[uv 0.12.22 release](https://github.com/astral-sh/uv/releases/tag/0.12.22).

## SDK 1.50.1 -> 1.51.0

| Upstream change | Decision | Evaluation |
| --- | --- | --- |
| #5151 agent profiles: `tools` is the only tool control; `enable_sub_agents` / `enable_switch_llm_tool` retired (deprecated 1.51.0, removal 1.56.0) | already adopted | Wire agents and commands already select tools through `tools:` / `allowed-tools:` frontmatter lists, and `task_tool_set` is how `/wire:design` enables sub-agent delegation (`SUB_AGENT_TOOL_NAME` unchanged). No plugin switch references the retired flags. Docs should keep pointing users at `task_tool_set` in `tools`, never `enable_sub_agents`. |
| #5358 keep delegated sub-agents within the profile's tools and MCP servers | monitor | Delegation via `task_tool_set` is now clamped to the launching profile's tool/MCP catalog. Wire sub-agents declare `tools:` and `mcp_config.wire` per AgentDefinition; a launching profile that omits the wire MCP server or an agent's tools will scope the sub-agent down accordingly. Plugin definition lists stay as the declared need — no change required here, but profile catalogs must cover `wire` MCP + declared tools for delegation to work end to end. |
| #5406 launch every agent through resolve and finalize | adopted with the pin | Internal unification of the agent launch path; AgentDefinition resolution behavior is preserved. |
| #5449 let a profile replace the agent's persona | not adopted | Server-side profile feature; wire agents keep their own prompts/personas at the plugin boundary. |
| #5450 loaded tools supply their system-prompt guidance (browser) | not adopted | Mechanism is for SDK builtin tools; wire's MCP server exposes deterministic entry points only and plugin guidance stays in skills/agent prompts per convention. |
| #5332 resolve `prompt_cache_key` via real provider for proxied models; #5274 OpenRouter verified provider; #5417 `/switch_llm` provider connection; #5412 direct-routing classifier messages | adopted with the pin | Provider/LLM-layer fixes that the VibeBB model profiles (`vibebb-author`, `vibebb-review`) inherit transparently; no profile fields change. |
| #5434 deprecate `ACPAgentSettings.llm` | not applicable | No ACP agent configuration in this repo. |
| #1326 fix `find_dotenv` assertion error in local conversation | adopted with the pin | Bug fix on the local-conversation path plugins run on; inherits automatically. |
| #5419 pydantic 2.13.5 in SDK deps | consistent | Repo already pins `pydantic>=2` and the lock resolves 2.13.5; the SDK floor now matches. |
| #5425, #5428 TypeScript client deps; #4945, #5415 CI fixes; #5397 stress-test slot | not applicable | TypeScript client and upstream CI changes; nothing to adopt at the plugin boundary. |

## uv 0.12.21 -> 0.12.22

| Upstream change | Decision | Evaluation |
| --- | --- | --- |
| Record default groups / dependency-group Python requirements in lockfiles | adopted inherently | `uv lock` revision 3 -> 5 now records `default-groups = ["dev", "sdk-check"]` on the project entry; frozen consumers read it back. |
| Verify unchanged requirements against existing lockfile hashes when relocking; workspace-member recorded-group fixes | adopted with the pin | Relock-integrity fix; benefits every `uv lock --upgrade` run. |
| New CPython builds (3.10.22/3.11.17/3.12.15/3.13.16/3.14.8) | inherent | The tools image installs Python `3.12` via `uv python install`; the newest patch lands automatically on the next image build. |
| `UV_PYTHON_ARCH` interpreter-architecture selector | not adopted | Single-arch (linux x86_64) image and CI; no cross-arch interpreter selection needed. |
| `uv audit` preview: `--no-default-groups`, offline error clarity | not adopted | Preview feature behind `uv audit`; the repo does not use `uv audit` (Trivy gates the image instead). |
| Uppercase wheel-tag suffixes, CLI URL/path formatting, `--offline` hidden from `uv publish` help, smaller binary, MSRV 1.97 | inherent | Tooling-internal changes; no repo behavior to adopt. |

## Compatibility deferrals

MCP 2.x remains deferred: SDK 1.51.0 still requires `fastmcp>=3.2.0,<4`,
which constrains `mcp<2` (lock resolves `mcp==1.30.0`,
`fastmcp==3.4.7`). See `scripts/dependency_update_deferrals.json`
(`latest` refreshed to 2.3.0).

## Lock scope

`uv.lock` was refreshed with `uv lock --upgrade` under uv 0.12.22. Direct
pins changed: `openhands-sdk` / `openhands-tools` 1.50.1 -> 1.51.0 and the
`[tool.uv]` required-version pin 0.12.21 -> 0.12.22 (Dockerfile
`ARG UV_VERSION` + `ARG UV_DIGEST` moved with it). All other diff churn is
transitive resolution drift within existing constraints; ruff was already
at 0.16.10 and stays.

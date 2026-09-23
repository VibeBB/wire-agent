# plugins/wire

OpenHands plugin assets for wire-agent. The deterministic core lives in
`src/wire`; everything here steers it — nothing here can pass a design.

- `skills/` — `wire-workflow` (orchestration), `wire-contract` (schema
  authoring), `wire-gates` (repair loop), `wire-connectivity` (imports)
- `agents/` — task sub-agents: `wire-brief` (intake conversation),
  `wire-design` (author → gates loop), `wire-review` (advisory)
- `commands/` — `/wire:design`, `/wire:doctor`, `/wire:gates`, `/wire:export`
- `hooks/` — session doctor, `protect-generated` artifact guard, stop-time
  status report
- `.mcp.json` — registers the `wire` stdio MCP server (thin wrapper over
  `src/wire`)
- `scripts/wire_launcher.py` — resolves the `wire` package matching the
  installed plugin and execs it inside the pinned `wire-tools` image
  (`docker run`), so every hook/MCP/CLI call runs against containerized
  dependencies; `python3 <launcher> <args>` mirrors `python -m wire`

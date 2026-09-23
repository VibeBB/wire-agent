---
description: Probe the wire harness tool environment.
allowed-tools:
  - terminal
---
Inside OpenHands, wire commands run inside the pinned tools image via the
plugin launcher. Resolve the plugin root the same way the hooks do
(`$WIRE_PLUGIN_ROOT`, `${OPENHANDS_PROJECT_DIR}/plugins/wire`,
`~/.agents/plugins/wire`, `~/.openhands/plugins/installed/wire`) into
`$WIRE_PLUGIN`, then call `python3 "$WIRE_PLUGIN/scripts/wire_launcher.py"
<args>`. In a repo checkout, `uv run python -m wire <args>` is equivalent.


Run `python3 "$WIRE_PLUGIN/scripts/wire_launcher.py" doctor` (or the `wire_doctor` MCP tool) and report the
JSON verdict and each check verbatim. A `fail` capability means the
environment cannot author or verify contracts — name the failing capability
and stop; do not proceed to design work.

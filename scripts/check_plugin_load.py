"""Load plugins/wire through the OpenHands SDK plugin loader and assert the
expected agents, skills, commands, hooks, and manifest version.

Exits 0 on success and prints a one-line summary; exits 1 listing every
mismatch. Intended for the `plugin-load` CI job.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = REPO_ROOT / "plugins" / "wire"

EXPECTED_AGENTS = {"wire-brief", "wire-design", "wire-review"}
EXPECTED_SKILLS = {
    "wire-connectivity",
    "wire-contract",
    "wire-gates",
    "wire-workflow",
}
EXPECTED_COMMANDS = {"design", "doctor", "export", "gates"}
EXPECTED_STOP_HOOKS = {"report-design-status"}
EXPECTED_PRE_TOOL_USE_HOOKS = {"protect-generated"}
EXPECTED_SESSION_START_HOOKS = {"wire-doctor"}


def _registered_tools() -> set[str]:
    """Import the builtin tool modules so their registrations exist."""
    import openhands.tools.preset.default  # pyright: ignore[reportMissingImports,reportMissingModuleSource]
    from openhands.sdk.tool.registry import (  # pyright: ignore[reportMissingImports,reportMissingModuleSource]
        list_registered_tools,
    )

    openhands.tools.preset.default.register_default_tools(enable_browser=False)
    import openhands.tools.glob.definition  # pyright: ignore[reportMissingImports,reportMissingModuleSource,reportUnusedImport]
    import openhands.tools.grep.definition  # pyright: ignore[reportMissingImports,reportMissingModuleSource,reportUnusedImport]
    import openhands.tools.task.definition  # pyright: ignore[reportMissingImports,reportMissingModuleSource,reportUnusedImport]

    return set(list_registered_tools())


def check_plugin(plugin_dir: Path) -> list[str]:
    """Return a list of mismatch reasons (empty means OK)."""
    from openhands.sdk.plugin import (  # pyright: ignore[reportMissingImports,reportMissingModuleSource]
        Plugin,
    )

    reasons: list[str] = []
    try:
        plugin = Plugin.load(plugin_dir)
    except Exception as e:
        return [f"Plugin.load failed: {e}"]

    manifest = json.loads((plugin_dir / ".plugin" / "plugin.json").read_text(encoding="utf-8"))
    if plugin.manifest.version != manifest.get("version"):
        reasons.append(
            f"manifest version {plugin.manifest.version!r} != "
            f"plugin.json {manifest.get('version')!r}"
        )

    agents = {a.name for a in plugin.agents}
    if agents != EXPECTED_AGENTS:
        reasons.append(f"agents {sorted(agents)} != {sorted(EXPECTED_AGENTS)}")

    skills = {s.name for s in plugin.skills}
    if skills != EXPECTED_SKILLS:
        reasons.append(f"skills {sorted(skills)} != {sorted(EXPECTED_SKILLS)}")

    commands = {c.name for c in plugin.commands}
    if commands != EXPECTED_COMMANDS:
        reasons.append(f"commands {sorted(commands)} != {sorted(EXPECTED_COMMANDS)}")

    if plugin.hooks is not None:
        collected: dict[str, set[str]] = {
            "session_start": set(),
            "pre_tool_use": set(),
            "stop": set(),
            "post_tool_use": set(),
        }
        for event_name in collected:
            groups: list[Any] = getattr(plugin.hooks, event_name, None) or []
            for group in groups:
                hooks: list[Any] = list(group.hooks)
                names = [h.name for h in hooks if h.name is not None]
                collected[event_name].update(names)
        if collected["session_start"] != EXPECTED_SESSION_START_HOOKS:
            reasons.append(
                f"session_start hooks {sorted(collected['session_start'])} != "
                f"{sorted(EXPECTED_SESSION_START_HOOKS)}"
            )
        if collected["pre_tool_use"] != EXPECTED_PRE_TOOL_USE_HOOKS:
            reasons.append(
                f"pre_tool_use hooks {sorted(collected['pre_tool_use'])} != "
                f"{sorted(EXPECTED_PRE_TOOL_USE_HOOKS)}"
            )
        if collected["stop"] != EXPECTED_STOP_HOOKS:
            reasons.append(
                f"stop hooks {sorted(collected['stop'])} != {sorted(EXPECTED_STOP_HOOKS)}"
            )

    registered = _registered_tools()
    for agent in plugin.agents:
        for tool in agent.tools:
            if tool not in registered:
                reasons.append(f"agent {agent.name!r} tool {tool!r} not registered")
    for command in plugin.commands:
        for tool in command.allowed_tools:
            if tool not in registered:
                reasons.append(f"command {command.name!r} allowed-tool {tool!r} not registered")
    return reasons


def main() -> int:
    reasons = check_plugin(PLUGIN_DIR)
    if reasons:
        for reason in reasons:
            print(reason)
        return 1
    print(
        "plugin-load OK: agents={wire-brief,wire-design,wire-review} "
        "skills={wire-connectivity,wire-contract,wire-gates,wire-workflow} "
        "commands={design,doctor,export,gates} "
        "hooks={wire-doctor,protect-generated,report-design-status}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

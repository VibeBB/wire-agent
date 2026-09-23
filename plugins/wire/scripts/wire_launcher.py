"""Resolve the wire package that matches the installed plugin, then exec.

Plugin installs update the assets under plugins/wire but do not reinstall
the `wire` Python package, so `python3 -m wire.*` may import a stale
site-packages copy that lacks the tools the assets expect. This launcher
points PYTHONPATH at a source tree consistent with the plugin before execing
the requested module.

Resolution order (first directory containing wire/__init__.py wins):
  1. $WIRE_SRC
  2. newest ~/.openhands/cache/extensions/wire-agent-*/src
  3. /opt/wire/src (wire-server image)
  4. <repo>/src when running from a repository checkout
  5. none found -> fall back to the already-installed package
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_MODULES = {"mcp_server": "wire.mcp_server", "doctor": "wire.cli"}


def _candidates(plugin_root: Path) -> list[Path]:
    candidates: list[Path] = []
    env_src = os.environ.get("WIRE_SRC")
    if env_src:
        candidates.append(Path(env_src))
    cache = Path.home() / ".openhands" / "cache" / "extensions"
    try:
        if cache.is_dir():
            candidates.extend(
                sorted(
                    cache.glob("wire-agent-*/src"),
                    key=lambda path: path.stat().st_mtime,
                    reverse=True,
                )
            )
    except OSError:
        pass
    candidates.append(Path("/opt/wire/src"))
    candidates.append(plugin_root.parent.parent / "src")
    return candidates


def resolve_source(plugin_root: Path) -> Path | None:
    for candidate in _candidates(plugin_root):
        try:
            if (candidate / "wire" / "__init__.py").is_file():
                return candidate.resolve()
        except OSError:
            continue
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("module", choices=sorted(_MODULES))
    parser.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    plugin_root = Path(__file__).resolve().parents[1]
    source = resolve_source(plugin_root)
    env = dict(os.environ)
    if source is not None:
        env["PYTHONPATH"] = (
            str(source) + os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else str(source)
        )
    if args.module == "doctor":
        argv = [sys.executable, "-m", "wire.cli", "doctor", *args.args]
    else:
        argv = [sys.executable, "-m", _MODULES[args.module], *args.args]
    os.execvpe(argv[0], argv, env)
    return 0


if __name__ == "__main__":
    sys.exit(main())

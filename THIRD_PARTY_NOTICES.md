# Third-Party Notices

wire is licensed BSD-3-Clause (see LICENSE). This file lists the third-party
components the project depends on and how they are used.

## Runtime dependencies (import-linked)

| Package | License | Use |
| --- | --- | --- |
| [pydantic](https://github.com/pydantic/pydantic) | MIT | Schema validation for contract/intake/report contracts |
| [mcp](https://github.com/modelcontextprotocol/python-sdk) | MIT | stdio MCP server boundary |
| [openhands-sdk](https://github.com/OpenHands/software-agent-sdk) 1.49.x | MIT | Plugin framework (skills, agents, commands, hooks, task sub-agents) |
| openhands-tools 1.49.x | MIT | SDK builtin tools used by sub-agents |

Indirect dependencies pinned in `uv.lock` follow each distribution's own
metadata on PyPI.

## Container image components

The `wire-tools` image bundles the following third-party components:

| Component | License | Use |
| --- | --- | --- |
| [drawio-desktop](https://github.com/jgraph/drawio-desktop) 31.4.5 | Apache-2.0 (bundles Electron/Chromium under their own licenses) | `drawio -x` renders the harness diagram and `--drawio` review outputs; runs unmodified under `xvfb-run` |
| fonts-ipafont | IPA Font License Agreement v1.0 | CJK glyph coverage for diagram text |
| Xvfb (xserver-xorg) | MIT/X11 | Headless display for drawio-desktop |
| uv (binary, copied from `ghcr.io/astral-sh/uv`) | Apache-2.0 OR MIT | Python environment and interpreter provisioning |
| Debian base image (`debian:13-slim`) | various (per-package copyrights in `/usr/share/doc/`) | base image + system libraries |

The drawio `.deb` is pinned by `DRAWIO_DESKTOP_VERSION` and verified against
`DRAWIO_DESKTOP_SHA256` at image build time.

## Development tools

| Tool | License |
| --- | --- |
| ruff | MIT |
| pyright | MIT |
| pytest / pytest-xdist | MIT |
| uv | Apache-2.0/MIT |
| zizmor | MIT |
| hatchling | MIT |

No copyleft (GPL/AGPL/LGPL) code is import-bound; copyleft tools may only
run as unmodified subprocesses behind an adapter. This file is not legal
advice.

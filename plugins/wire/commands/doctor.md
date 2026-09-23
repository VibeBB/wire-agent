---
description: Probe the wire harness tool environment.
allowed-tools:
  - terminal
---

Run `python -m wire doctor` (or the `wire_doctor` MCP tool) and report the
JSON verdict and each check verbatim. A `fail` capability means the
environment cannot author or verify contracts — name the failing capability
and stop; do not proceed to design work.

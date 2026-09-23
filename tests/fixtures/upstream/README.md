# Upstream contract fixtures

Canonical samples of the ADR-0003 contract files that upstream plugins emit:

- `board.connectivity.json` — a `ConnectivitySource` as produced by
  electrical-circuit-agent's `python3 -m circuit.connectivity_export` /
  `circuit_connectivity_export` MCP tool.
- `housing.envelope.json` — an `EnvelopeSource` as produced by
  mechanical-agent's `python -m mech export-envelope` / `mech_export_envelope`
  MCP tool.

The wire-agent importer is the schema's source of truth
(`src/wire/imports.py`). electrical-circuit-agent and mechanical-agent keep
golden copies under their own `tests/fixtures/` so their emitters are pinned
against the same payloads; when the schema changes here, update all copies.

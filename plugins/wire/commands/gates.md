---
description: Re-run all deterministic gates on a harness contract.
argument-hint: <contract.json> [out_dir]
allowed-tools:
  - terminal
---

Run `python -m wire gates --contract <file> --out <out_dir>` (omit `--out`
only to skip the artifact manifest check) and report each non-pass check
verbatim — id, subject, status, measured, limit. `unknown` fails closed: an
unmeasured gate is a failing gate. Do not edit artifacts; repairs happen in
the contract and are re-checked by `wire_author`.

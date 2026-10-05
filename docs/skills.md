# Skills

Skills live in `plugins/wire/skills/<name>/SKILL.md`.

| Skill | Trigger | Purpose |
| --- | --- | --- |
| `wire-workflow` | "wire harness", "ワイヤハーネス", "配策", "harness design", "wire-agent" | Orchestrates brief → design → review → liaison answer with `TaskToolSet`; vision uses; domain coverage; boundaries; imported connectivity; UX liaison (SLP v2); VRP records. |
| `wire-contract` | used by `wire-brief` | How to author a `HarnessContract` and its intake sidecar: element ids, provenance binding, open questions, evidence references. |
| `wire-contract-rules` | path rule on `*.contract.json` / `*.intake.json` | Short schema and provenance reminders injected whenever a contract or intake file is touched. |
| `wire-gates` | used by `wire-design` | Every gate, what makes it fail or `unknown`, and how to repair the contract instead of the artifacts. |
| `wire-connectivity` | imports | `wire_import` kinds (`circuit-json`, `csv`, `mech-envelope`), source shapes, `I*` provenance and re-import behavior. |

## Key rules the skills enforce

- The contract and intake are the truth; artifacts are projections.
- Gate JSON is the only pass/fail authority; `unknown` fails closed.
- Images inform `A*`/`Q*` records, never `R*`; every viewed image gets a
  vision review with a long-form impression.
- Sister cooperation goes through workspace files (imports, `liaison/`),
  never package imports.
- The terminal runs one command per call; chain with `&&`.

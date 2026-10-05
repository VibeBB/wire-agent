# Commands

## Slash commands (`plugins/wire/commands/`)

| Command | Arguments | What it does |
| --- | --- | --- |
| `/wire:design` | `<project_dir> <requirements summary>` | Full workflow: liaison check, `wire-brief` until intake `ready`, `wire-design` until gates pass, mandatory `wire-review`, liaison answers, summary. |
| `/wire:doctor` | — | Runs `wire doctor` through the launcher and reports the tool environment. |
| `/wire:gates` | `<contract.json> [out_dir]` | Re-runs every gate; with `out_dir` also checks `manifest_integrity`. |
| `/wire:export` | `<contract.json> <out_dir>` | Writes projections without gates; `--drawio`/`--png` add renders that must then be vision-reviewed. |

## CLI (`python -m wire`, or `wire_launcher.py <args>` inside OpenHands)

Every subcommand prints one JSON object; the exit code is 0 only for a
passing verdict (`pass`/`ready`).

| Subcommand | Arguments | Result |
| --- | --- | --- |
| `doctor` | `[--warn]` | Tool probe (python, drawio, xvfb, versions). `--warn` never fails the session hook. |
| `intake` | `--contract F --intake F` | Intake report, verdict `ready`/`blocked`. |
| `author` | `--contract F --out D [--png] [--drawio FMTS] [--baseline JSON]` | Export + gates + `design-report.json/.md`. |
| `export` | `--contract F --out D [--png] [--drawio FMTS] [--baseline JSON]` | Projections + manifest only. |
| `gates` | `--contract F [--out D]` | Gate report. |
| `import` | `--contract F --from circuit-json\|csv\|mech-envelope --source F [--out F]` | Merged contract (in place unless `--out`). |
| `drawio` | `--in F [--out F] [--format F] [--baseline JSON] [drawio -x options...]` | Proxy for `drawio -x`. |
| `drawio-lint` | `--in F [--out F]` | Advisory readability lint. |
| `review-record` | `--image F --model M --checklist C (--impression T \| --impression-file F) --findings F [--summary S] [--out D]` | Typed advisory vision record bound to the image sha256. |
| `record` | `decision\|impression\|vision-review --json F`, or `status` | VRP record writers and status. |
| `ux` | `inbox`, or `respond --json F` | SLP v2 inbox and response writer. |

`--drawio` takes a comma list of `png,jpg,pdf,html,svg,xml`; `--png` is
shorthand for `--drawio png`. `--baseline` records or compares the
`harness-diagram.png` sha256.

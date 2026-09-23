# wire-agent

An OpenHands plugin for conversational wire harness design — requirements
in, verified manufacturing data out.

wire-agent turns a requirements conversation into a machine-readable
harness contract, verifies it with deterministic gates, and projects it
into manufacturing artifacts: wire list, cut table, BOM, and a harness
diagram. The same JSON file is both the design and the authority; nothing
a model says can override a gate verdict.

## What it does

- **Conversational intake** — clarifies electrical, environmental, and
  mechanical requirements and writes `<name>.contract.json` plus an
  intake sidecar that binds every element to requirement (`R*`),
  assumption (`A*`), question (`Q*`), or imported-source (`I*`) ids.
- **Deterministic verification** — L1 gates check connectivity, cavity
  occupancy, ampacity with temperature/bundle derating, voltage drop,
  insulation rating, bend radius, signal segregation, terminal
  compatibility, and connector ratings. `unknown` fails closed.
- **Manufacturing projections** — `wire-list.csv`, `cut-table.csv`,
  `bom.json/.csv`, and `harness-diagram.drawio.svg` — a WireViz-style
  pin-table diagram rendered by drawio-desktop, viewable as SVG and
  editable in diagrams.net (a raw `.drawio` mxfile when drawio is
  absent) — with sha256 manifest and provenance records. `--drawio`
  adds png/jpg/pdf/html/svg/xml review renders; `wire_drawio` (MCP) and
  `python -m wire drawio` proxy the full `drawio -x` CLI surface.
- **Plugin cooperation** — imports connectivity from
  electrical-circuit-agent contracts or generic CSV tables, consumes
  envelope anchors from mechanical-agent, and emits artifacts
  bard-agent can sing about. No acd-agent dependency.

## Layout

```text
src/wire/          deterministic core (contract, gates, export, MCP)
plugins/wire/      OpenHands plugin (skills, agents, commands, hooks)
tests/  scripts/   verification
examples/          sample harness contract
docs/adr/          design decisions   docs/research/   domain survey
docker/            tools image definition + digest lock
```

## Quick start

```bash
uv sync
uv run python -m wire doctor
uv run python -m wire intake \
  --contract examples/sensor-harness/sensor-harness.contract.json \
  --intake  examples/sensor-harness/sensor-harness.intake.json
uv run python -m wire author \
  --contract examples/sensor-harness/sensor-harness.contract.json \
  --out out/sensor-harness
```

The verdict is `pass` only when every gate check reports `pass`.

In an OpenHands conversation, install `plugins/wire` and run `/wire:design`
(or `task` the `wire-brief` sub-agent). See
[docs/architecture.md](docs/architecture.md) and the
[ADR index](docs/README.md) for the full model.

## Verification

```bash
uv run python scripts/verify_all.py --stage fast
```

See [AGENTS.md](AGENTS.md) for the working agreement,
[CONTRIBUTING.md](CONTRIBUTING.md) for contributor setup, and
[docs/operations.md](docs/operations.md) for release and CI policy.

---

# wire-agent（日本語）

対話形式でワイヤハーネスを設計する OpenHands プラグインです。要件の
会話から機械可読なハーネス契約（contract.json）を生成し、決定論的
ゲートで検証し、ワイヤリスト・カットテーブル・BOM・ハーネス図へ投影
します。設計と権威は同じ JSON です。モデルの発言がゲート判定を
上書きすることはありません。

## できること

- **対話による要件取り込み** — 電気・環境・機械要件を明確化し、
  contract.json と intake（R*/A*/Q*/I* 由来記録）を出力します。
- **決定論的検証** — 接続性・キャビティ占有・許容電流（温度/束
  ディレーティング）・電圧降下・絶縁定格・曲げ半径・信号分離・
  端子適合・コネクタ定格を L1 ゲートで検査。`unknown` は失敗扱い。
- **製造投影** — `wire-list.csv` `cut-table.csv` `bom.json/.csv`
  `harness-diagram.drawio.svg`（WireViz 風ピンテーブル図。drawio-desktop
  で描画され、SVG として表示でき、diagrams.net で編集可能。
  drawio 不在時は生の `.drawio` mxfile を出力）を sha256 マニフェスト・
  由来記録付きで出力。`--drawio` で png/jpg/pdf/html/svg/xml の
  レビュー用レンダリングも追加可能。`wire_drawio`（MCP）と
  `python -m wire drawio` は `drawio -x` の全機能をプロキシします。
- **プラグイン連携** — electrical-circuit-agent の契約や汎用 CSV から
  接続情報を取り込み、mechanical-agent のアンカー契約を参照し、
  bard-agent が歌にできる標準成果物を出力。acd-agent への依存はありません。

詳細は [docs/README.md](docs/README.md) と各 ADR を参照してください。

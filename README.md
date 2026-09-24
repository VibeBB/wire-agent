# wire-agent

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/VibeBB/wire-agent)

Part of the [VibeBB](https://github.com/VibeBB) agent family:
[bard-agent](https://github.com/VibeBB/bard-agent) ·
[electrical-circuit-agent](https://github.com/VibeBB/electrical-circuit-agent) ·
[mechanical-agent](https://github.com/VibeBB/mechanical-agent) ·
[wire-agent](https://github.com/VibeBB/wire-agent)

[English](#english) | [日本語](#日本語)

## English

An [OpenHands](https://github.com/OpenHands) plugin for conversational wire
harness design — requirements in, verified manufacturing data out.

wire-agent turns a requirements conversation into a machine-readable
harness contract, verifies it with deterministic gates, and projects it
into manufacturing artifacts: wire list, cut table, BOM, and a harness
diagram. The same JSON file is both the design and the authority; nothing
a model says can override a gate verdict.

### What it does

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
  pin-table diagram rendered by drawio-desktop (shipped in the pinned
  wire-tools image; the export fails closed without it), viewable as SVG and
  editable in diagrams.net — with sha256 manifest and provenance
  records. `--drawio`
  adds png/jpg/pdf/html/svg/xml review renders; `wire_drawio` (MCP) and
  `python -m wire drawio` proxy the full `drawio -x` CLI surface.
  `wire_author`/`wire_drawio` attach the rendered raster inline as MCP
  `ImageContent` for vision-capable models, `--baseline` records the
  image sha256 for deterministic change detection, and vision reviewers
  write typed `review-visual-<slug>.advisory.json` records (L2
  advisory only — never gate verdicts).
- **Plugin cooperation** — imports connectivity from
  electrical-circuit-agent contracts or generic CSV tables, consumes
  envelope anchors from mechanical-agent, and emits artifacts
  bard-agent can sing about. No acd-agent dependency.

### Layout

```text
src/wire/          deterministic core (contract, gates, export, MCP)
plugins/wire/      OpenHands plugin (skills, agents, commands, hooks)
tests/  scripts/   verification
examples/          sample harness contract
docs/adr/          design decisions   docs/research/   domain survey
docker/            tools image definition + digest lock
```

### Quick start

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

### Verification

```bash
uv run python scripts/verify_all.py --stage fast
```

See [AGENTS.md](AGENTS.md) for the working agreement,
[CONTRIBUTING.md](CONTRIBUTING.md) for contributor setup, and
[docs/operations.md](docs/operations.md) for release and CI policy.

### License

BSD-3-Clause © VibeBB — see [LICENSE](LICENSE) and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## 日本語

[OpenHands](https://github.com/OpenHands) 向けの会話型ワイヤハーネス設計
プラグインです — 要件を入力し、検証済みの製造データを得られます。

wire-agent は要件の会話を機械可読なハーネス契約に変換し、決定論的
ゲートで検証し、製造成果物（ワイヤリスト・カットテーブル・BOM・
ハーネス図）へ投影します。設計と権威は同じ JSON です。モデルの発言が
ゲート判定を上書きすることはありません。

### できること

- **対話による要件取り込み** — 電気・環境・機械要件を明確化し、
  `<name>.contract.json` と intake サイドカー（全要素を要求 `R*`・
  仮定 `A*`・質問 `Q*`・インポート元 `I*` の各 ID に紐付け）を出力
  します。
- **決定論的検証** — 接続性・キャビティ占有・許容電流（温度/束
  ディレーティング）・電圧降下・絶縁定格・曲げ半径・信号分離・
  端子適合・コネクタ定格を L1 ゲートで検査。`unknown` は失敗扱い。
- **製造投影** — `wire-list.csv` `cut-table.csv` `bom.json/.csv`
  `harness-diagram.drawio.svg`（WireViz 風ピンテーブル図。digest 固定の
  wire-tools イメージ同梱の drawio-desktop で描画され、SVG として表示でき、
  diagrams.net で編集可能。drawio 不在時はエクスポートが fail-closed で失敗）を
  sha256 マニフェスト・由来記録付きで出力。`--drawio` で png/jpg/pdf/html/svg/xml の
  レビュー用レンダリングも追加可能。`wire_drawio`（MCP）と
  `python -m wire drawio` は `drawio -x` の全機能をプロキシします。
  `wire_author`/`wire_drawio` は描画ラスタを MCP `ImageContent` として
  インライン添付し、`--baseline` が画像 sha256 を記録して決定論的に
  変化を検出します。vision レビューは型付き
  `review-visual-<slug>.advisory.json` レコードを書きます（L2
  アドバイザリのみ — ゲート判定には昇格しません）。
- **プラグイン連携** — electrical-circuit-agent の契約や汎用 CSV から
  接続情報を取り込み、mechanical-agent のエンベロープアンカー契約を
  参照し、bard-agent が歌にできる成果物を出力。acd-agent への依存は
  ありません。

### 構成

```text
src/wire/          決定論コア（契約・ゲート・エクスポート・MCP）
plugins/wire/      OpenHands プラグイン（skills, agents, commands, hooks）
tests/  scripts/   検証
examples/          サンプルハーネス契約
docs/adr/          設計決定          docs/research/   領域調査
docker/            ツールイメージ定義 + digest ロック
```

### クイックスタート

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

すべてのゲート検査が `pass` を報告したときのみ判定は `pass` です。

OpenHands の会話では `plugins/wire` をインストールし `/wire:design`
を実行します（または `wire-brief` サブエージェントへ `task`）。
詳細は [docs/architecture.md](docs/architecture.md) と
[ADR 索引](docs/README.md)を参照してください。

### 検証

```bash
uv run python scripts/verify_all.py --stage fast
```

作業規約は [AGENTS.md](AGENTS.md)、コントリビュータのセットアップは
[CONTRIBUTING.md](CONTRIBUTING.md)、リリース・CI 方針は
[docs/operations.md](docs/operations.md)を参照してください。

### ライセンス

BSD-3-Clause © VibeBB — [LICENSE](LICENSE) と
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)を参照してください。

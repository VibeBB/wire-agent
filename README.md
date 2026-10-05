# wire-agent

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/VibeBB/wire-agent)

[English](#english) | [日本語](#日本語)

## English

wire-agent is the wiring member of [VibeBB](https://vibebb.org/), a family
of AI plugins for designing hardware products by conversation. You tell
it what your product's cables have to connect and survive; it gives you a
checked harness design and the files a workshop needs to build it.

### What it does for you

- **Asks the right questions.** Which parts connect, how much current
  flows, how hot it gets, where the cable runs and how often it bends.
  Anything it is unsure about becomes a question for you, not a guess.
- **Checks the design with fixed rules, not opinions.** Wire size against
  current and heat, voltage loss, insulation, bend radius, separation of
  noisy and sensitive signals, connector ratings, whether every route is
  long enough to reach the mounting points from the mechanical design,
  and more. If something cannot be checked, the design does not pass.
- **Produces build files.** A wire list, a cut table (lengths, strip
  lengths, terminals), a bill of materials, a harness drawing on a
  standard drawing sheet, and a route plan that shows the cable path over
  the mechanical mounting points.
- **Looks at its own drawings.** Every drawing it makes, and every photo
  you share, is inspected by a vision-capable model, and the reading is
  written down. The checks still decide pass or fail; the visual review
  helps catch what rules cannot see.
- **Explains itself.** Each important choice is recorded with the reasons
  behind it, and each stage ends with a written impression, so you can
  see why the design looks the way it does.

### What you give and what you get

| You give | You get |
| --- | --- |
| A description of the product, its connectors and signals | A harness design file (`*.contract.json`) and a list of open questions |
| Optional: pinout photos, sketches, datasheet tables | Readings of those images, kept as assumptions you confirm |
| Optional: files from sister plugins (circuit, mechanical) | A design that follows the circuit's nets and the mechanical mounting points |
| Answers to its questions | Wire list, cut table, BOM, harness drawing, route plan, a pass/fail report |

### Working with the sister plugins

wire-agent works alongside the other VibeBB plugins through files in the
same project folder:

- **UX-creator** directs the team. It leaves a request in `liaison/`;
  wire-agent answers with what it delivered and whether every check
  passed. It will not say "done" while a check fails.
- **electrical-circuit** supplies the connections between parts.
- **mechanical** supplies the mounting points (clips, grommets) and
  their positions.
- **production-engineering**, **document**, **dashboard** and **bard**
  use wire-agent's outputs for manufacturing plans, documents, status
  views and songs.

Sister plugins: [UX-creator](https://github.com/VibeBB/UX-creator-agent) ·
[bard](https://github.com/VibeBB/bard-agent) ·
[dashboard](https://github.com/VibeBB/dashboard-agent) ·
[document](https://github.com/VibeBB/document-agent) ·
[electrical-circuit](https://github.com/VibeBB/electrical-circuit-agent) ·
[firmware](https://github.com/VibeBB/firmware-agent) ·
[fpga](https://github.com/VibeBB/fpga-agent) ·
[mechanical](https://github.com/VibeBB/mechanical-agent) ·
[production-engineering](https://github.com/VibeBB/production-engineering-agent) ·
[simulation](https://github.com/VibeBB/simulation-agent)

### Getting started (AgentCanvas / OpenHands)

1. Install Docker on the machine that runs the agent. wire-agent runs
   all of its tools inside a pinned container image; nothing else needs
   to be installed.
2. Add the plugin from `https://github.com/VibeBB/wire-agent` (folder
   `plugins/wire`) in AgentCanvas or OpenHands.
3. Start a conversation and describe your cable, or type `/wire:design`.
   For example: "A 12 V sensor cable from the controller board to two
   sensors in the lid; the lid opens about 500 times."
4. Answer the questions. When every check passes, the files appear in
   `out/<name>/` in your project folder.

### Limits and safety

- Cable routes are described, not computed in 3D. The tool checks that a
  route is at least long enough to reach its mounting points, not that it
  avoids every obstacle.
- There is no nail-board (formboard) layout or KBL/VEC export yet.
- Visual reviews are advice. They can stop a design, never pass one.
- Tools run in an isolated container without network access. Generated
  files cannot be edited by hand; fixes go into the design file.
- A passing report is not a safety certification. Have a qualified
  person review designs for mains voltage, vehicles, medical or other
  regulated uses.

Technical documentation: [docs/README.md](docs/README.md). Contributors:
[AGENTS.md](AGENTS.md), [CONTRIBUTING.md](CONTRIBUTING.md).

License: BSD-3-Clause © VibeBB — see [LICENSE](LICENSE) and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## 日本語

wire-agent は、会話でハードウェア製品を設計する AI プラグイン群
[VibeBB](https://vibebb.org/) の配線担当です。製品のケーブルが何をつなぎ、
どんな環境に耐える必要があるかを伝えると、検証済みのハーネス設計と、
工場で作るためのファイル一式を返します。

### できること

- **必要なことを質問します。** どの部品をつなぐか、流れる電流、温度、
  ケーブルの通り道、曲げの回数など。分からないことは推測せず、あなたへの
  質問にします。
- **意見ではなく決まったルールで検査します。** 電流と熱に対する電線の太さ、
  電圧降下、絶縁、曲げ半径、ノイズの多い信号と繊細な信号の分離、コネクタ
  定格、機械設計の取付点まで経路が届く長さがあるか、など。検査できない
  項目があれば合格になりません。
- **製造用ファイルを作ります。** ワイヤリスト、カットテーブル（長さ・
  皮むき長・端子）、部品表、標準図枠付きのハーネス図、機械の取付点の上に
  ケーブル経路を描いた配策図。
- **自分の図を目で確認します。** 作った図面と、あなたが共有した写真は
  すべて画像を読めるモデルが確認し、その所見を記録します。合否は検査が
  決め、目視レビューはルールで見えない問題を見つける助けになります。
- **理由を説明します。** 重要な判断はその理由とともに記録され、各段階の
  終わりには所感が書かれるので、設計がなぜこうなったかを追えます。

### 渡すものと受け取るもの

| 渡すもの | 受け取るもの |
| --- | --- |
| 製品、コネクタ、信号の説明 | ハーネス設計ファイル（`*.contract.json`）と未解決の質問 |
| 任意: ピン配置の写真、スケッチ、データシートの表 | それらの画像の読み取り結果（あなたが確認する仮定として保持） |
| 任意: 姉妹プラグイン（回路・機械）のファイル | 回路のネットと機械の取付点に沿った設計 |
| 質問への回答 | ワイヤリスト、カットテーブル、BOM、ハーネス図、配策図、合否レポート |

### 姉妹プラグインとの連携

wire-agent は、同じプロジェクトフォルダ内のファイルを通じて他の VibeBB
プラグインと協力します。

- **UX-creator** がチームを指揮します。`liaison/` に依頼を置くと、
  wire-agent は納品物とすべての検査に合格したかを返答します。検査が
  失敗している間は「完了」と答えません。
- **electrical-circuit** は部品間の接続を提供します。
- **mechanical** は取付点（クリップ、グロメット）とその位置を提供します。
- **production-engineering**、**document**、**dashboard**、**bard** は
  wire-agent の出力を製造計画、文書、状況表示、歌に使います。

姉妹プラグイン: [UX-creator](https://github.com/VibeBB/UX-creator-agent) ·
[bard](https://github.com/VibeBB/bard-agent) ·
[dashboard](https://github.com/VibeBB/dashboard-agent) ·
[document](https://github.com/VibeBB/document-agent) ·
[electrical-circuit](https://github.com/VibeBB/electrical-circuit-agent) ·
[firmware](https://github.com/VibeBB/firmware-agent) ·
[fpga](https://github.com/VibeBB/fpga-agent) ·
[mechanical](https://github.com/VibeBB/mechanical-agent) ·
[production-engineering](https://github.com/VibeBB/production-engineering-agent) ·
[simulation](https://github.com/VibeBB/simulation-agent)

### はじめかた（AgentCanvas / OpenHands）

1. エージェントを動かすマシンに Docker をインストールします。wire-agent
   はすべてのツールを固定されたコンテナイメージ内で実行するため、他に
   インストールするものはありません。
2. AgentCanvas または OpenHands で `https://github.com/VibeBB/wire-agent`
   （フォルダ `plugins/wire`）のプラグインを追加します。
3. 会話を始めてケーブルを説明するか、`/wire:design` と入力します。
   例:「制御基板から蓋の中の 2 つのセンサーへ行く 12 V のセンサー
   ケーブル。蓋は約 500 回開閉します。」
4. 質問に答えます。すべての検査に合格すると、プロジェクトフォルダの
   `out/<name>/` にファイルが出力されます。

### 制限と安全

- ケーブル経路は記述されたもので、3D で計算されたものではありません。
  経路が取付点に届く長さがあるかは検査しますが、すべての障害物を避けるか
  は検査しません。
- 釘板（フォームボード）レイアウトと KBL/VEC 出力はまだありません。
- 目視レビューは助言です。設計を止めることはあっても、合格させることは
  ありません。
- ツールはネットワークのない隔離コンテナで動きます。生成ファイルは手で
  編集できず、修正は設計ファイルに対して行います。
- 合格レポートは安全認証ではありません。商用電源電圧、車両、医療など
  規制のある用途では、資格のある人に設計を確認してもらってください。

技術ドキュメント: [docs/README.md](docs/README.md)。コントリビュータ向け:
[AGENTS.md](AGENTS.md)、[CONTRIBUTING.md](CONTRIBUTING.md)。

ライセンス: BSD-3-Clause © VibeBB — [LICENSE](LICENSE) と
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) を参照してください。

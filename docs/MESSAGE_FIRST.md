# メッセージから資料を作る

通常の入口は `$slides-create` 一つ。内部で文章設計、配置設計、制作、レビューを進める。
ここで扱う `story.yaml` と `layout.yaml` は既存の生成用 `plan.yaml` とは別の成果物であり、
従来のplanから直接ビルドする使い方も維持する。

## 1. 文章で論証を作る

最初に、聴衆に持ち帰ってほしいメッセージを1〜2文にする。続いて、文章だけを読んでも
説明として成立する段落を並べる。前に導入した概念を受けて、後の概念・主張が必要になる
順序にする。見出しで情報を分類しただけでは、この順序は決まらない。

システム研究なら、次の関係を必要に応じて整理する。すべての資料にこの項目数を強制しない。

- 関係者は誰で、それぞれにどのようなニーズ・情報・役割があるか。
- 背景の変化、ありたい姿と現状の差から、なぜ研究目的が生まれるか。
- 目的を実現するために何が課題となり、どの着想で解こうとするか。
- 提案する全体構想、本稿の具体的な貢献、その実現に必要な要素技術の関係。
- 実験が何を検証し、結果がどの主張をどこまで裏付けるか。
- そこから何が言え、次に何を行うか。

用語を使う前に定義し、同じ概念の名前を途中で変えない。名詞だけの箇条書きに省略しすぎず、
主語と述語を持つ短い文章を使う。読み上げれば説明になる文章は、論証の飛躍を見つける助けにもなる。
技術の原典・引用、図の由来、実測結果と設計例も整理する。目的や期待する効果を実測値に置き換えない。
確認した結果と今後の展開を自然に書き分け、発表資料へ不要な責任回避文を付け足さない。

### Story形式

```yaml
message: 状態名と短い説明文を組み合わせた架空の表示案を説明する。
audience: ロボットの状態表示を検討する読者
purpose: 説明用の表示案と，表示内容を整理する手順を示す
concepts:
  - id: state
    label: 状態の分類
    definition: 待機・実行中・確認待ちという説明用の分類。
assets:
  - id: process_figure
    path: figures/process.svg
    source: サンプル用に作成する架空の図
    role: 状態名と説明文の対応を示す
sections:
  - id: proposal
    role: 状態の整理
    claim: 架空の状態の分類を用意する。
    body: 待機・実行中・確認待ちを説明用の状態の分類とする。特定の製品や業務は想定しない。
    introduces: [state]
    evidence: [process_figure]
  - id: requirement
    role: 表示内容
    claim: 状態名に短い説明文を付けて表示する。
    body: 状態の分類に応じて，状態名と短い説明文を組み合わせる。利用者実験は実施していない。
    depends_on: [proposal]
    uses: [state]
```

これは形式の例であり、特定研究の実験結果ではない。完全な動作例は
`examples/message_first_story.yaml` と `examples/message_first_layout.yaml`。

`message` と1つ以上の `sections` が必要。各節には `id`、`claim`、実際の説明文 `body` を書く。
`role` は任意の分類名。`concepts`、`assets` と関連付けは必要な場合に使う。

| フィールド | 意味 |
|---|---|
| `introduces` | その節で初めて定義するconcept ID |
| `uses` | その節より前の節で導入したconcept ID |
| `depends_on` | 説明の前提となる、前のsection ID |
| `evidence` | 説明または裏付けに使うasset ID |

概念を導入する節では、その概念を `introduces` に書く。同じ節で使い始める概念を
`uses` にも二重記載する必要はない。細かな説明順が重要なら節を分ける。

```bash
structured-slide-creator story check story.yaml
structured-slide-creator story md story.yaml --out story.md
```

検査はIDの重複、存在しない参照、未導入の概念への参照、依存順序などを調べる。
文章の意味、因果の妥当性、証拠の十分さを自動で認定するものではない。Markdownには
メッセージと本文がそのまま出るので、文章として読んで確かめる。

## 2. 文章を配置へ展開する

配置は各段落を説明するための領域である。段落と図表を関連付けてから、大きさ、位置、
読む順序を決める。関連する説明を近づけ、要素技術を全体提案に従属させるなど、
論理的な関係が視覚的にも読み取れるようにする。

論文の図表はまず再利用を検討する。新たな説明図は、言葉だけでは理解しにくい概念や
仕組みを具体化するために用いる。図の大きさはその役割と視認性から決め、巨大な数値や
均等な箱を並べることで面積を埋めない。図には必要な文脈を与えてから見せる。

用紙・投影サイズ、読む距離、印刷倍率、最小文字サイズは資料ごとに決める。
今回指定された16ptやA3、色帯などを全資料に固定しない。枠が足りなければ文章・配置・
図の説明方法を見直し、決めた文字サイズを黙って小さくしない。

### Layout形式

```yaml
story: story.yaml
page: {width_mm: 297, height_mm: 420}
typography: {label_pt: 16, title_pt: 28}
pages:
  - id: poster
    label: 論理の流れを確認する配置案
    reading_order: [title, process, reuse]
    regions:
      - id: title
        label: 正式タイトルの領域
        kind: title
        box_mm: [10, 10, 277, 35]
        priority: context
      - id: process
        label: 状態名と説明文の対応
        kind: figure
        box_mm: [10, 55, 277, 170]
        sections: [proposal]
        assets: [process_figure]
        purpose: 状態の分類と表示内容の対応を説明する
        priority: primary
      - id: reuse
        label: 表示内容の整理
        kind: body
        box_mm: [10, 235, 277, 170]
        sections: [requirement]
        purpose: 状態名に説明文を付ける関係を説明する
        priority: supporting
```

この座標は形式を示す例であり、すべての資料に推奨する配置ではない。
`page` は全ページ共通のmm寸法。`pages` にページ、`regions` に領域を定義する。
ページIDは文書全体で、領域IDは同じページ内で一意にする。

`box_mm` は `[左, 上, 幅, 高さ]`。`sections` と `assets` はstoryのIDを参照する。
`purpose` または `reason` に、なぜその場所・面積が必要かを書く。
`priority` は `primary` / `supporting` / `context`。`kind` は予定する内容の種類で、
`title`、`body`、`figure`、`table`、`footer` など短い名前を使う。
`label_pt` は領域ごとにも指定できる。

`reading_order` はそのページの領域IDを読む順序で列挙する。省略時は領域の記載順になる。
明示した順序から漏れた領域は記載順に末尾へ追加され、警告される。節が複数領域に現れる場合、
最初の登場を導入位置として扱う。依存を逆転する配置はエラーになる。
意図的な抜粋では未配置の節は警告となるため、出力した指摘を読んで前提不足を確認する。

```bash
structured-slide-creator layout check layout.yaml
structured-slide-creator layout md layout.yaml --out layout.md
structured-slide-creator layout build layout.yaml --out poster_layout.pptx --theme academic
structured-slide-creator review poster_layout.pptx --sources story.yaml layout.yaml
```

wireframeはネイティブ図形・テキストによる配置案。短い領域名と予定する図表IDなどを示し、
本文・実画像・結果の数値を埋め込まない。実画像を開いたり、custom_scriptを実行したりしない。
素材が未提供でも領域を予約できる。入力の相対パスは各YAML/JSONファイルの位置が基準となる。

宣言した座標・ラベル寸法・参照と順序を検査する。図表と本文の最終的な収まりや
物理的な読みやすさの証明にはならない。実際に描画し、全体・必要な拡大画像を確認する。
ラベル自体が入らない枠は、ラベルを短くするか領域を見直す。黙って縮小しない。

## 3. 内容を配置し、二つの確認を行う

内容入り資料は、確認した配置を基に既存の生成用plan・ヘルパーで作る。
`layout build` は配置案の生成専用であり、文章を自動で図へ解釈したり、内容入り資料まで
自動変換したりするコマンドではない。`slides-create` が図表・本文を配置し、
必要なら配置を更新した理由を記録する。小さな変更では既存の論証や配置を保つ。

```bash
structured-slide-creator plan check plan.yaml
structured-slide-creator build plan.yaml --out presentation.pptx --theme academic
structured-slide-creator review presentation.pptx --sources story.yaml layout.yaml plan.yaml generator.py
```

`--sources` は存在する生成元だけを明示する。ツールはPPTX、画像、指定された生成元を
ハッシュで関連付けるが、ソースを読んだことや画像を見たことは自動認定しない。
表示上の問題だけでなく、数値・用語・引用・原図の意味・読む順序も確認する。
PPTXがレンダリング中に変わった場合も、別版を見たこととして扱わない。

新しい配置と完成版の画像確認は、この環境で利用できるAstraに依頼する。
指定モデルが使えない場合は代替と確認範囲を正しく記録する。レビューには実際に表示した画像、
ページ、正確なPPTX/画像のハッシュ、指摘、修正結果を残す。
修正後は再ビルド・再描画し、新しい版を再確認する。レイアウトの確認は完成版の確認を含まない。

CLIで成功しても、意味が伝わること、実験の妥当性、視覚レビューの完了を保証しない。
ユーザーへは論理構造、配置案、内容入り初版を節目として示し、完成まで依頼されている場合は
すでにある権限で制作と検証を続ける。不要なスキル切替や承認待ちは新設しない。

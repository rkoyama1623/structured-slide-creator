# structured-slide-creator 設計書（実装方針・残作業つき）

最終更新: 2026-11-18 / 対象: structured-slide-creator

このドキュメントだけ読めば、別の PC でも実装を再開できることを目標にしている。
**生成・CLI・構造検査・匿名化解析・スキル同期を実装済み**。検証範囲と制約は §8 に記載する。

---

## 1. 設計の中心的な考え方

参考記事（Insight Edge Tech Blog「PowerPoint 自動生成で AI にデザインさせるのをやめた」）から
採った原則は次の 3 点。

1. **伝える文章と論理構造から配置を決め、共通の描画規則はコードに置く。**
   AIは原稿を読み、概念の導入順・主張と証拠の関係・面積配分を設計する。
   フォント・配色・罫線などの再利用可能な既定はヘルパーとテーマで管理する。
   既存の美しい配置を選ぶだけでは、メッセージや論証の設計にはならない。
2. **規則はプロンプトではなく例外で守らせる。**
   「12pt 未満にしない」と書いても AI は破る。下限を割ったら `DesignRuleError` を投げて
   ビルドを止める（`src/structured_slide_creator/design/rules.py`）。
3. **人が後から編集できる PPTX を出す。**
   テキストはテキストボックス、表はネイティブ表、グラフはネイティブチャート、
   図はネイティブ図形＋コネクタ。スライドを画像化して貼る方式は採らない。

記事から **変えた** 点は 2 つ。

- **1 スライド＝1 ビルドスクリプト**ではなく、**完成版の内容をplan(YAML)に記録するデータ駆動**にした。
  本文・論証はstory、先行する配置設計はlayoutに分け、完成版のplanへ反映する。
  手で座標を作り込みたい例外のために `layout: custom_script` の逃げ道を残してある。
- **企業テンプレートを一切読み込まない。** `Presentation()`（python-pptx 既定の空ファイル）の
  白紙レイアウトだけを使い、プレースホルダも削除して、見た目は全部テーマから描く。

### 「生成AIっぽさ」を避けるための具体的な制約

テーマ側で既定を落としてある（`styles/*.yaml` の `layout:`）。

| 項目 | 既定 | 実装箇所 |
|---|---|---|
| 影 | 無効（`shadow.inherit = False`） | `shapes.kill_effects()` |
| グラデーション | 使わない | 塗りは `solid` のみ |
| 角丸 | 0（直角） | `shape_corner_radius: 0.0` |
| アイコン | 仕組みとして持たない | — |
| カード状の箱 | 「弱い面」＋罫線なしに限定 | `add_note_block`, 比較列の見出し帯 |
| 強調 | 左縦罫（`add_key_message`）で、文字を大きくしない | `components.add_key_message` |
| 同一レイアウトの連続 | 4 枚続くと plan 検証が警告 | `plan/schema.py` |

---

## 2. 全体アーキテクチャ

制作の順序は **メッセージの文章 → story（論証・概念の順序）→ layout（主張・図表の配置）
→ 編集可能なワイヤフレーム → 内容入りplan → PPTX → ソースと描画画像の確認**。
入口は `slides-create` 一つで、必要な内部スキルだけを読む。
`message_first/` はstoryとlayoutの参照・幾何を検査し、ネイティブ図形の配置案を出す。
本文や図を自動投入する仕組みではなく、科学的な正しさも判定しない。
詳細は [MESSAGE_FIRST.md](MESSAGE_FIRST.md)。既存のplan直接ビルドも維持する。

```
          plan (YAML)            ← 文章と配置の設計を反映した完成版の生成入力
              │
              ▼
  ┌───────────────────────┐
  │ plan/schema.py        │  検証（未知レイアウト・情報量・レイアウト単調さ）
  └───────────┬───────────┘
              ▼
  ┌───────────────────────┐
  │ generation/layouts.py │  意味的レイアウト 23 種（「何のためのページか」で選ぶ）
  │   ↓ 領域(Box)を決める  │
  │ generation/blocks.py  │  領域に何を描くかのディスパッチャ（19 ブロック型）
  │   ↓                   │
  │ components / diagram  │  公開ヘルパ API（＝承認済みデザイン）
  │ tables / charts       │
  │   ↓                   │
  │ generation/shapes.py  │  python-pptx の薄いラッパ（塗り・罫線・影・余白の既定値）
  └───────────┬───────────┘
              ▼
        output/*.pptx  +  *.manifest.json
              │
      ┌───────┴────────┐
      ▼                ▼
 rendering/        review/           ← Step 4: 画像化 → 自動検査 → AI 視覚レビュー
 (PowerPoint COM)  (checks.py)
```

テーマ（`styles/neutral.yaml` / `academic.yaml`）が全レイヤに効く唯一のデザイン定義。
`academic` は `extends: neutral` で**差分だけ**を持つ（独立テンプレートにしない）。

### ディレクトリ

```
structured-slide-creator/
├── docs/ARCHITECTURE.md      ← この文書
├── pyproject.toml
├── styles/{neutral,academic}.yaml
├── src/structured_slide_creator/
│   ├── units.py              Box（inch 基準の矩形）— レイアウト計算の唯一の通貨
│   ├── textmetrics.py        文字幅の概算（生成時と検査時で同じ基準を使う）
│   ├── design/               tokens.py / rules.py / contrast.py
│   ├── generation/           shapes → components/diagram/tables/charts → blocks → layouts → build
│   ├── plan/                 schema.py / io.py
│   ├── rendering/            base.py / powerpoint_com.py / libreoffice.py
│   ├── review/               実装済み：checks.py / report.py
│   ├── analysis/             実装済み：ローカル抽出・匿名化・カタログ
│   └── cli.py                実装済み
├── skills/                   canonical な SKILL.md 5 本（入口1・内部4）
├── .claude/skills/           ← skills/ から同期（コピー）
├── .agents/skills/           ← skills/ から同期（コピー）
├── references/{raw,sanitized}/   raw は .gitignore 済み
├── design_catalog/
├── examples/demo_research.yaml   架空の状態表示の説明資料 11 枚（動作確認用）
├── output/                   .gitignore 済み
└── tests/                    回帰・CLI・解析・描画テスト
```

---

## 3. 採用ライブラリと理由

| ライブラリ | 用途 | 選定理由 |
|---|---|---|
| **python-pptx 1.0.2** | PPTX 生成・解析 | OOXML を直接書かずにネイティブオブジェクト（表・チャート・コネクタ）を作れる。解析にも同じ API が使える |
| **PyYAML** | テーマ・plan・カタログ | 人間が読み書き・レビューできる。JSON より構成案に向く |
| **Pillow** | 画像サイズ取得／匿名化ワイヤフレーム生成 | 既にインストール済み。軽量 |
| **pywin32 (COM)** | PowerPoint ネイティブレンダリング | 実機と同じピクセルで視覚レビューできる。この PC で動作確認済み |
| **pytest** | テスト | 標準 |
| （任意）PyMuPDF | 非 Windows の PDF→PNG | LibreOffice 経路のため。`render` extraで導入。構造検査には不要 |

**使わないもの**: LLM へ OOXML を直接書かせる構成、HTML→画像、スライド画像の貼り付け、
外部のテンプレート/テーマファイル（企業ブランドの混入経路になるため）。

---

## 4. デザインルールとレイアウトの管理方法

### 4.1 トークン（`styles/*.yaml`）

`fonts` / `colors` / `type`(19 スタイル) / `layout`(余白・行間・罫線) / `footer` / `limits` / `conventions`。
`Theme.style("body")` のように論理名で引き、色は `"accent"` などのキー名か `#RRGGBB`。

`limits` が強制される下限・上限（`design/rules.py`）:

| キー | neutral | academic | 役割 |
|---|---|---|---|
| `min_body_pt` | 12.0 | 13.0 | 本文・箇条書き・リード・見出し |
| `min_table_pt` | 11.0 | 12.0 | 表セル |
| `min_font_pt` | 9.5 | 10.5 | キャプション・注記・図中ラベル |
| `min_chrome_pt` | 8.5 | 8.5 | フッタ・ページ番号 |
| `max_bullets` / `max_chars_per_slide` / `max_flow_steps` ほか | | | 情報量の上限（超過は警告、重大なら例外） |

**はみ出しの扱い**: `textmetrics.measure()` で必要高さを概算し、枠の 112% を超えたら例外。
文字を縮めるのではなく「項目を減らす／言い換える／分割する／図解にする」を促すメッセージを出す。

### 4.2 レイアウトカタログ

`generation/layouts.py` の `LayoutSpec` が、記事でいう「承認済みデザイン」のメタ情報を持つ。

```python
LayoutSpec(
    id="results_chart", purpose="実験結果（グラフ）",
    description="左にグラフ、右に読み取れること（箇条書き）。逆配置も可",
    suited_for=["評価結果", "比較実験", "計測結果"],
    volume="グラフ 1 点＋所見 2〜4 件",
    functions=["add_chart", "add_bullet_list", "draw_split_layout"],
    cautions=["軸ラベルと単位を必ず入れる", "与えられていない数値を作らない"],
    keys=[...],
)
```

実装済み 23 種:
`title_cover / section_divider / agenda / bullets / text_figure / figure_text / two_column /
comparison / problem_solution / process_flow / system_diagram / algorithm / timeline / roadmap /
experiment_setup / results_chart / table / evaluation_matrix / image_focus / summary / closing /
free / custom_script`

`catalog_entries()` で辞書化でき、解析で得た知見と統合して
`design_catalog/catalog.yaml` に出力 → 人間が `status: accepted|rejected|revise` を付ける運用。

### 4.3 ブロック型（レイアウト数を増やさずに表現力を出す仕組み）

`blocks.render_block(ctx, box, spec)`。レイアウトは領域だけ決め、中身はこの 19 型から選ぶ:
`text / bullets / key_message / note / caption / formula / image / figure / chart / table /
matrix / flow / steps / diagram / timeline / roadmap / compare / split / empty`

`split` は入れ子にできるので、「左は箇条書き＋注記、右はグラフ」といった組み合わせが
新レイアウトを足さずに書ける。

---

## 5. 過去資料の解析方法

**ローカル構造解析と、LLM に渡す情報を分離する**のが大前提。

```
references/raw/*.pptx   （.gitignore 済み・外部送信しない）
      │  ① python-pptx による構造抽出（ローカル完結）
      ▼
analysis/extract.py → slides[].shapes[] の幾何・書式 JSON
      │  ② ブランド依存要素の分離（自動判定は「候補」止まり）
      ▼
analysis/brand.py → brand_flags（理由つき・inherit=False 既定・要人間確認）
      │  ③ 意味的レイアウト分類（規則ベース＋特徴量）
      ▼
analysis/classify.py → layout_type + confidence + evidence
      │  ④ 匿名化（本文は文字数・字種だけに潰す／参照画像はワイヤフレーム）
      ▼
analysis/sanitize.py → references/sanitized/*.json, design_catalog/generated/*.png
      │  ⑤ カタログ統合（status: proposed → 人間が採用/不採用/修正）
      ▼
design_catalog/catalog.yaml
```

### 抽出する項目
スライドサイズ・比率／マスタ・レイアウト名／図形種別と座標寸法／フォント・サイズ・色／
テキスト階層／余白と要素間隔／図表と説明文の位置関係／情報密度（文字数・図形数・占有率）／
レイアウト類似度（正規化した占有矩形のヒストグラム比較）。

### ブランド依存の判定（継承しないもの）
- マスタ/レイアウトに置かれた画像、全スライド共通の隅の小さな画像 → ロゴ候補
- 企業コーポレートカラーに近い色（判定は候補提示のみ。**ヒューリスティックで確定させない**）
- 部署名・会社名・定型表記の正規表現（`株式会社|（株）|本部|センタ` 等）
- 権利確認できない画像・アイコン → `inherit: false` 固定

判定結果は `needs_human_review: true` を付けて出力し、`slides-tune` で採否を確定する。

### 継承する（学ぶ）もの
情報構造と論理展開／1 枚あたりの情報量／タイトル・リード・本文の階層／図表と文の配置関係／
概念図・構成図・フロー図の描き方／比較表・評価マトリクス・時系列の型／余白と整列の癖。

---

## 6. Skill・コマンド構成（Claude Code / Codex 両対応）

このプロジェクトで同期する配置:

| | Claude Code | Codex |
|---|---|---|
| 置き場所 | `.claude/skills/<name>/SKILL.md`（プロジェクト）、`~/.claude/skills/`（個人） | `.agents/skills/<name>/SKILL.md`（リポジトリ、上方向に探索）、`$HOME/.agents/skills/` |
| 必須 frontmatter | `name`, `description` | `name`, `description` |
| 明示呼び出し | `/slides-create ...` | `$slides-create ...` |
| 自動呼び出し | `description` で判断 | `description` で判断（`agents/openai.yaml` で抑制可） |

→ **frontmatter は Agent Skills 標準の共通集合（`name` / `description` / `license` /
`compatibility` / `metadata` / `allowed-tools`）だけ使えば、1 本の SKILL.md が両方で動く。**

したがって実体は `skills/<name>/SKILL.md` に 1 本だけ置き、
`structured-slide-creator skills sync` で `.claude/skills/` と `.agents/skills/` へコピーする
（Windows では symlink が管理者権限を要するためコピー＋ハッシュ比較の `skills check` を用意）。

通常の入口は1本、内部スキルは4本。

| Skill | 役割 | 中心コマンド |
|---|---|---|
| `slides-create` | 文章・論証を決め、必要な工程を内部で進める入口 | `structured-slide-creator story check/md` |
| `slides-layout` | 主張・図表に対応する領域と読む順序を設計 | `structured-slide-creator layout check/md/build` |
| `slides-review` | ソース実読、画像化、自動検査、実画像の確認 | `structured-slide-creator review <pptx> --sources ...` |
| `slides-tune` | 指定修正と、その資料固有か共通規則かの判断 | `structured-slide-creator tune` ほか |
| `slides-analyze` | 指定された過去PPTXの配置傾向を解析 | `structured-slide-creator analyze --input <dir>` |

ユーザーに複数スキルの使い分けを求めない。Codex向けの内部スキルには
`allow_implicit_invocation: false` を置く。本文・メタデータ・補助資源を再帰同期する。

### ワークフロー

1. 原稿を読み、中心的な主張と、それに至る説明文を作る。概念を定義した後に使う。
2. storyの主張・前提・図表に基づきlayoutを作る。利用可能ならAstraへ配置設計を依頼する。
3. 内容を入れる前の編集可能な配置案を生成・描画して確認する。配置案だけの依頼ならここまで。
4. 完成までの依頼では制作を続ける。既存図表を優先してplanとヘルパーで内容を入れる。
5. 生成ソースと実際の描画画像を両方確認する。利用可能ならAstraへ画像確認を依頼する。
   機械検査の成功や画像生成を承認扱いにしない。変更後は再描画する。

小さな修正で論証設計を毎回やり直さない。承認待ちはユーザーが指定した場合に限る。
ユーザーの文字サイズや色の好みを全資料の固定規則にせず、目的・閲覧条件に合わせる。

---

## 7. 機密情報・知的財産の扱い

- 解析対象は**ユーザーが明示指定したディレクトリのみ**（`--input` 必須。既定値を持たせない）。
- `references/raw/`、`*.pptx`、`design_catalog/generated/*.png` は `.gitignore` 済み。
- 構造解析は**ローカル完結**。LLM に渡すのは匿名化後の JSON とワイヤフレーム画像だけ。
- 配置傾向を学ぶ参照資料の別研究の本文は流用しない。ユーザーが制作素材として提供した
  自分の原稿・図表は、正確に再利用する。カタログに保存するのは抽象構造のみ。
- Claude Code / Codex でのモデル処理も外部送信に当たるため、`slides-analyze` の SKILL.md に
  「raw の中身を会話に貼らない」ことを明記する。

---

## 8. 実装と検証

- `review/checks.py`: スライド外・重なり・近接整列・フォント下限・低コントラスト・
  タイトル位置/サイズ・情報量・表/テキストあふれ・画像縦横比を検査。
- `review/report.py`: review.json / review.md / images.json と画像を生成。
  画像出力後の `visual_review: pending` と `source_review: pending` は実読・実視認の未確認を示す。
  PPTX・指定ソース・画像のSHA-256を記録し、生成中の変化はstaleとして扱う。
- `cli.py`: build / render / check / review / story / layout / plan / analyze / catalog / skills /
  themes / doctor / tune。`python -m structured_slide_creator` も同じ入口。
- `analysis/`: ローカル抽出、ブランド候補、規則分類、allowlistによる匿名化、
  ワイヤフレーム、正規化占有グリッド、採否を保持するカタログ統合。
- `skills/`: 5本の正本。`skills_sync.py` がコピーと差分検知を担当。
- `setup.py`: wheelへテーマ・スキル・ドキュメントを同梱。

検証は `python -m pytest`。両テーマの11枚サンプル、全23レイアウト・19ブロック、
不正plan、相対画像パス、ノート、表のあふれ、匿名化と採否保持、CLI、スキル差分を確認する。
LibreOfficeがある環境では選択ページのPNG出力も実行する。

修正済みの生成不具合:
コネクタと図形のstyle effectRefに残る影、短い矢印を覆うラベル、
構成図のグループ見出しの本文領域外への突出、表の折り返しに不足する固定行高、
同一レーンの予定バーの重なり、結びページの出典重複、
ノート文字列の1文字ずつの分割、テーマフォントXMLの保存漏れ。

### 制約

文字寸法・重なり・近接整列・レイアウト分類は推定で、人の確認を置き換えない。
文字のない背景面、注記、エッジラベルは重なりから除外する。意図した包含も検出する場合がある。
回転・複雑なグループ座標変換・継承色・チャート内部の文字には画像確認が必要。
ブランド判定は組織名表記や隅の画像などからの候補で、企業色やロゴの完全な識別器ではない。
カタログのacceptedは採用記録であり、描画コードの自動拡張ではない。
PowerPoint COMの動作はWindowsとPowerPointのある実機で別途確認する。
LinuxではLibreOfficeの近似描画を利用し、既定フォント不足はdoctorで診断する。

通常の操作と終了コードは [README](../README.md)、APIは [HELPERS](HELPERS.md) を参照。

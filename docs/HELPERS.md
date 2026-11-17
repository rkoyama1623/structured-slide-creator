# ヘルパーリファレンス

プロジェクトルートで `structured-slide-creator --help`。Python APIは `src/structured_slide_creator/`。
寸法は inch、フォントは pt。`Box(x, y, w, h)` が領域の共通形式。

| モジュール | API | 用途 |
|---|---|---|
| plan | `load_plan(path)`, `save_plan(plan, path)` | YAML/JSON入出力。画像・scriptの相対パスはplan基準 |
| plan | `validate_plan(plan)`, `plan_to_markdown(plan)` | 構成検査、人間向け要約 |
| design.tokens | `load_theme(name_or_path)`, `available_themes()` | テーマ取得。extendsは同じディレクトリの親を優先 |
| generation | `build_deck(plan, out=..., theme=None, only=None)` | PPTXとmanifest。only指定時は対象だけのPPTX |
| generation.layouts | `catalog_entries()`, `LAYOUTS` | 23種のレイアウトと用途・入力キー |
| generation.components | `add_slide_title(ctx, title, lead=None)` | タイトル、リード、本文領域 |
| generation.components | `add_body_text(ctx, box, text)`, `add_bullet_list(ctx, box, items)` | 本文、階層付き箇条書き |
| generation.components | `add_key_message`, `add_note_block`, `add_caption`, `add_reference_note` | 主張・注記・出典 |
| generation.components | `add_image_with_caption(ctx, box, image_path, caption=...)` | 比率を保つ画像配置 |
| generation.diagram | `draw_split_layout(ctx, box, ratios=...)` | 分割領域の作成 |
| generation.diagram | `draw_comparison_layout(ctx, box, columns)` | 見出し付き比較 |
| generation.diagram | `draw_process_flow`, `draw_step_list`, `draw_system_diagram` | フロー・手順・構成図 |
| generation.diagram | `draw_timeline`, `draw_roadmap`, `add_formula` | 時系列・予定・数式 |
| generation.tables | `make_table(ctx, box, header, rows, col_ratios=...)` | 行高を内容から見積もる編集可能な表 |
| generation.tables | `make_matrix(ctx, box, options, criteria, ratings, comments=...)` | 評価表 |
| generation.charts | `add_chart(ctx, box, kind, categories, series)` | PowerPointで編集可能なチャート |
| generation.blocks | `render_block(ctx, box, block)`, `render_stack(...)` | 内容ブロックの描画 |
| rendering | `render_pptx(path, out_dir, renderer='auto')` | PowerPoint COM優先、LibreOfficeへフォールバック |
| review | `check_pptx(path, theme='neutral')`, `review_pptx(path, out_dir, ...)` | 構造検査、画像・レポート出力 |
| analysis | `analyze_directory(input_dir, out_dir)` | 指定フォルダだけを解析して匿名化 |

正確なキーワード引数は該当関数のdocstring/シグネチャを読む。

## 文章・配置の設計

通常の入口は `slides-create`。内部の `slides-layout` が文章の論証に沿って配置を設計する。
[制作手順とYAML形式](MESSAGE_FIRST.md) を参照。既存のplan APIはそのまま利用できる。

| モジュール | API | 用途 |
|---|---|---|
| message_first | `load_story`, `validate_story`, `story_to_markdown` | 主張・本文・概念の導入順と図表参照 |
| message_first | `load_layout`, `validate_layout`, `layout_to_markdown` | 実寸の領域・読む順序・主張と図表の対応 |
| message_first | `build_layout(document, out=..., theme=...)` | 内容を入れない編集可能な配置案 |
| review | `verify_review_bindings(report)` | 記録したPPTX・ソース・画像のハッシュ照合 |

`story check` は参照や順序、`layout check` は寸法や読み順との対応を検査する。
文章の妥当性や図表の意味を自動判定するものではない。本文入りの完成版には別途planを作り、
生成後にソースと実際の描画画像を確認する。

## planの最小例

```yaml
meta:
  title: プロジェクト報告
  theme: neutral
slides:
  - id: cover
    layout: title_cover
  - id: progress
    layout: bullets
    title: 試作版の動作を確認した
    bullets:
      - 確認できた事実を記載
      - 未確認事項は未確認と明示
```

23レイアウト: title_cover / section_divider / agenda / bullets / text_figure /
figure_text / two_column / comparison / problem_solution / process_flow / system_diagram /
algorithm / timeline / roadmap / experiment_setup / results_chart / table /
evaluation_matrix / image_focus / summary / closing / free / custom_script。

19ブロック: text / bullets / key_message / note / caption / formula / image / figure /
chart / table / matrix / flow / steps / diagram / timeline / roadmap / compare / split / empty。

`two_column` の `left` / `right` や `free` の `blocks` にブロックを置ける。
文字列はtext、リストは縦積み。`split` の `blocks` はさらに入れ子にできる。
`image`・`path`・`script` はファイルパス専用。相対パスはplanファイル基準で解決する。

## 検査の扱い

`must_fix` は明確な下限違反やスライド外。`should_fix` は修正を検討する項目、
`nice_to_fix` は整列候補。文字高さ、重なり、整列、分類は概算・規則ベース。
文字のない背景面と、注記・エッジラベルは重なり検査から除外される。複雑なグループの変換・回転・
テーマ継承色やグラフ内部文字の完全な見た目は画像で確認する。

`review.json` の `visual_review: pending` は画像出力済みで、人の視覚確認完了を意味しない。
`source_review: pending` もソースの実読を意味しない。`--sources` は指定ファイルのハッシュを記録する。
`artifact_status: stale` は生成中に入力が変化した状態で、再生成が必要。
`unavailable` はレンダラが使えなかった状態。LibreOffice出力は近似である。
CLI終了コードは0=成功、1=構成検証エラー/重大な検出/スキル差分、2=実行エラー。
警告だけの場合は0。`doctor`は診断結果をJSONで返し、環境不足もデータとして扱う。

# structured-slide-creator

公開用のソース一式です。サンプルは特定の企業・製品・研究を表さない架空の例です。

伝えたいメッセージを文章にし、概念の導入順と配置を決めてから、編集可能なPowerPointを生成するツールです。
図形・テキスト・表・チャートはPowerPointのネイティブ要素です。
文章の論証はstory、内容を入れる前の配置はlayout、完成版の内容はplanで管理します。
ヘルパーとテーマは共通の書式・描画規則を担当します。

- neutral / academicの2テーマ、継承・カスタムテーマ対応
- 23種類のレイアウト、19種類の内容ブロック
- フォント下限・情報量・はみ出しの検査
- PowerPoint COM / LibreOfficeによる画像化と品質レポート
- 指定フォルダのPPTXをローカル解析し、匿名化した配置カタログを作成
- Codex / Claude Code向けの入口スキル1本と内部スキル4本、コピー同期
- 概念・主張の参照順序検査と、実寸指定の編集可能なワイヤフレーム

## インストール

Python 3.10以上。リポジトリのルートで実行します。

```bash
python -m venv .venv
# Linux / macOS
source .venv/bin/activate
# Windows PowerShellの場合: .venv\Scripts\Activate.ps1
python -m pip install -e '.[dev,render]'
# PowerPointを使うWindowsでは追加:
# python -m pip install -e '.[win]'
structured-slide-creator doctor
```

PNG出力には、WindowsではPowerPoint + pywin32、その他ではLibreOfficeと
PyMuPDF（`render` extra）またはPopplerの `pdftoppm` が必要です。
PPTX生成と構造検査はレンダラなしで動きます。
Windows用の既定フォントが無い環境では代替フォントになります。
`doctor` で確認し、必要ならカスタムテーマでインストール済みのフォントを指定します。

## メッセージと配置を先に決める

通常は `$slides-create` に原稿と制作条件を渡します。内部で必要なスキルを読み、
文章設計 → 配置案 → 内容入り資料 → ソースと描画画像の確認を進めます。
配置案だけを依頼することもできます。小さな修正では必要な工程だけを使います。

```bash
structured-slide-creator story check examples/message_first_story.yaml
structured-slide-creator story md examples/message_first_story.yaml --out output/story.md
structured-slide-creator layout check examples/message_first_layout.yaml
structured-slide-creator layout md examples/message_first_layout.yaml --out output/layout.md
structured-slide-creator layout build examples/message_first_layout.yaml --theme academic --out output/layout_A3.pptx
structured-slide-creator review output/layout_A3.pptx --sources examples/message_first_story.yaml examples/message_first_layout.yaml
```

この例は架空のロボットの状態表示を説明するA3配置案です。`layout build` は短い領域名と図表IDを
ネイティブ図形・テキストで描き、本文や画像は挿入しません。完成版の制作には既存のplanと
ヘルパーを使います。文章の論理・科学的妥当性や実際の読みやすさは、機械検査とは別に確認します。
形式と制作手順は [メッセージから資料を作る](docs/MESSAGE_FIRST.md) を参照してください。

## サンプルを生成する

```bash
structured-slide-creator plan check examples/demo_research.yaml
structured-slide-creator plan md examples/demo_research.yaml --out output/plan.md
structured-slide-creator build examples/demo_research.yaml --theme academic --out output/demo_academic.pptx
structured-slide-creator review output/demo_academic.pptx
```

サンプルは架空のロボットの状態表示を題材にした11枚の説明資料です。
本文・数値・参考資料はサンプル専用で、実在の研究成果や利用者実験には基づきません。

`output/demo_academic.pptx` と隣接する `.manifest.json` が生成されます。
レビュー出力は `output/demo_academic/` 内の `review.md` / `review.json` /
`images.json` / `slides/slide01.png` …です。
`review` は画像を用意します。画像の視覚確認が終わったことは意味しません。
`--sources` で制作スクリプト・原稿を指定すると、PPTX・画像とともにSHA-256を記録します。
ソースと画像の確認状態は自動承認せず、ファイル変更後は再描画・再確認します。

```bash
# 一部ページだけを含む確認用PPTX
structured-slide-creator build examples/demo_research.yaml --out output/results.pptx --only results
# 構造だけを検査
structured-slide-creator check output/demo_academic.pptx --out output/check.json
structured-slide-creator review output/demo_academic.pptx --no-render
# PNG出力のみ
structured-slide-creator render output/demo_academic.pptx --out output/png --slides 4 7 9
# テーマ一覧
structured-slide-creator themes
```

`--only` は既存資料のページを置換せず、指定したページだけのPPTXを生成します。
最終版はplanから全ページを再ビルドしてください。
画像・スクリプトの相対パスはplanファイルのディレクトリを基準に解決します。
`custom_script` レイアウトはPythonを実行するため、信頼するローカルスクリプトを指定します。

## 過去資料から配置の候補を学ぶ

```bash
structured-slide-creator analyze --input /path/to/explicit/reference-directory --out references/sanitized
structured-slide-creator catalog export --out design_catalog/catalog.yaml
structured-slide-creator catalog merge --input references/sanitized --out design_catalog/catalog.yaml
structured-slide-creator tune <entry-id> --status accepted --comment 'この配置を採用'
```

解析は明示されたフォルダだけを再帰走査し、原本は変更しません。
本文・ファイル名・図形名・フォント名・元画像・ブランド色は匿名化出力に含めません。
出力は配置、文字数、文字サイズ、分類候補、ブランド候補とワイヤフレームです。
画像は権利未確認として継承不可、ブランド候補には人の確認が必要です。
カタログのマージは人が付けた採否・コメントを保持します。
`accepted` は候補の採用記録であり、新しい描画コードを自動追加するものではありません。

## エージェント向けスキル

正本は `skills/`。変更後は以下で `.agents/skills/` と `.claude/skills/` に同期します。

```bash
structured-slide-creator skills sync
structured-slide-creator skills check
```

通常の入口は `slides-create` 一つです。内部で `slides-layout` / `slides-review` /
`slides-tune` / 必要に応じて `slides-analyze` を使い、ユーザーに順番の指定を求めません。
内部スキルのCodex向けメタデータは暗黙の自動起動を抑制し、明示利用と内部参照は残します。
別ディレクトリへ配置する場合は `--root <directory>` を指定します。

## 検査の範囲と開発

- `must_fix`: スライド外へのはみ出し、フォント下限など。check/reviewは終了コード1。
- `should_fix`: 重なり、文字あふれ、低コントラスト、表のあふれ、比率崩れなどの修正候補。
- `nice_to_fix`: 近い端の整列候補。意図した内側余白も拾うため画像と照合します。
- 文字寸法・重なり・分類は概算です。回転・複雑なグループ変換・継承色・チャート内文字の
  完全な検証は画像で行います。LibreOffice描画はPowerPoint実機とは差が出ます。
- CLIは成功0、検証エラー・重大な検出・スキル差分1、実行失敗2。
  レンダラが使えないreviewは構造レポートを保存して2を返します。

```bash
python -m pytest
python -m build
```

テストは全レイアウト・全ブロック、両テーマ、匿名化、CLIなどを確認します。
LibreOfficeがある環境では実際の選択ページ画像化も検証します。
wheelにはテーマ・スキル・リファレンスも同梱されます。

[制作手順](docs/MESSAGE_FIRST.md) / [設計書](docs/ARCHITECTURE.md) / [ヘルパーAPI](docs/HELPERS.md)

## 機密情報

`references/raw/`、PPTX/PDF、生成物はGit管理対象外です。
原本の構造抽出はローカルで完結します。rawの本文や抽出結果を会話に貼らず、
必要な範囲の匿名化JSON・ワイヤフレームだけをレビュー対象にしてください。

原本資料・解析結果・生成物を追加する場合は、公開前に内容と権利を個別に確認してください。

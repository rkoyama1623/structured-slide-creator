---
name: slides-analyze
description: slides-createが必要時に内部で使う参考資料解析。明示された過去PPTXフォルダを匿名化し、配置候補をカタログへ統合する。
---

# Slides analyze

通常の入口は [slides-create](../slides-create/SKILL.md)。呼び出し元へ解析結果を返し、
ユーザーに次のスキルを起動するよう求めない。制作素材として提供された論文の図表を
使うことと、別の資料からデザイン傾向だけを学ぶことは区別する。

参照資料のデザインをそのまま複製しない。新しい資料では既存のヘルパーを使い、
分割には `draw_split_layout()`、表には `make_table()` を使う。
数値や参照資料の本文を新しい資料へ流用しない。APIは `docs/HELPERS.md` を参照する。

入力はユーザーが明示したディレクトリだけに限定する。指定が無い場合は対象を確認する。
ホームディレクトリやDrive全体を推測で走査しない。
raw PPTXの本文や抽出JSONを会話に貼らず、LLMや外部サービスへ送信しない。

1. `structured-slide-creator analyze --input <explicit-directory> --out references/sanitized` を実行する。
   再帰走査は指定ディレクトリ内のみ。原本は変更されない。
2. 出力のハッシュ名JSONとwireframesを確認する。本文・画像・元ファイル名・フォント名・
   ブランド色は出力されない。匿名化された配置情報も必要な範囲でのみ共有する。
3. `structured-slide-creator catalog merge --input references/sanitized --out design_catalog/catalog.yaml`。
   分類は規則に基づく候補で、confidenceとevidenceを確認する。
4. ブランド候補は人が確認するまで継承しない。画像は権利未確認として `inherit: false`。
   見出し・本文・図の関係や情報量だけを学ぶ。
5. 採否を確認してから `structured-slide-creator tune <entry-id> --status accepted|rejected|revise --comment <reason>`。
   マージは既存の採否を保持する。組み込みレイアウトを追加実装する際は別途生成と検査を行う。

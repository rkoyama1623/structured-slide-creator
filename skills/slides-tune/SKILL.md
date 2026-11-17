---
name: slides-tune
description: slides-createが内部で使う修正工程。修正の意図を説明文・配置・plan・テーマの適切な場所へ反映し、再生成する。
---

# Slides tune

通常の入口は [slides-create](../slides-create/SKILL.md)。ユーザーに別スキルへの切替を求めない。
修正がメッセージや概念の前提を変える場合は、文章→配置→内容の順に影響を確認する。
色や一語だけの修正なら、無関係な構成の作り直しはしない。

デザインはヘルパーに集約する。分割は `draw_split_layout()`、表は `make_table()`。
テーマの下限やヘルパーを迂回しない。数値・実験結果は創作しない。
APIと変更箇所は `docs/HELPERS.md` を参照する。

修正が「今回の資料のみ」か「今後の共通ルール」かを区別する。
ユーザーが既に範囲を指定していれば従う。不明ならplanへの局所修正を進め、
恒久ルールへの変更だけを確認する。

- 内容や配置の変更はplanに反映し、ビルドとレビューで確認する。
- 明示された共通ルールは `styles/*.yaml` のトークンまたはヘルパーへ反映する。
  neutralとacademicの両方でサンプルをビルドし、既存テストを実行する。
- 解析で得たカタログ候補の採否は
  `structured-slide-creator tune <entry-id> --catalog <path> --status accepted|rejected|revise --comment <reason>`。
  これは候補の記録を更新するコマンドで、テーマや描画実装を自動変更しない。
- スキルの変更は正本 `skills/<name>/SKILL.md` に行い、
  `structured-slide-creator skills sync` と `structured-slide-creator skills check` で両エージェント向けのコピーを揃える。

例外のためにフォント下限を全体で下げない。要約・分割・図解を優先する。

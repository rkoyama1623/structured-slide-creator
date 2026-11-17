"""意味的レイアウト（「何を伝えるためのページか」で選ぶ）。

各レイアウトは領域の切り方だけを決め、中身は blocks.render_block に委ねる。
レイアウトのメタ情報（用途・適した内容・推奨情報量・注意点）は LAYOUTS に持たせ、
デザインカタログとして人間が確認・修正できるように YAML へ書き出せる。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ..design.rules import DesignRuleError
from ..units import Box, pt_to_inches
from . import components as C
from . import diagram as D
from . import shapes as S
from .blocks import render_block, render_stack
from .deck import SlideCtx


@dataclass
class LayoutSpec:
    id: str
    purpose: str                      # 用途
    description: str                  # レイアウト構造の説明
    suited_for: list[str]             # 適したコンテンツ
    volume: str                       # 推奨情報量
    functions: list[str]              # 対応する描画関数
    cautions: list[str] = field(default_factory=list)
    keys: list[str] = field(default_factory=list)   # spec で使う主なキー
    build: Callable[[SlideCtx, dict], None] | None = None


LAYOUTS: dict[str, LayoutSpec] = {}


def layout(spec: LayoutSpec):
    def deco(fn):
        spec.build = fn
        LAYOUTS[spec.id] = spec
        return fn

    return deco


def build_slide(ctx: SlideCtx, spec: dict) -> None:
    """1 枚分の仕様からスライドを描く。"""
    name = str(spec.get("layout", "bullets"))
    if name not in LAYOUTS:
        raise DesignRuleError(
            f"unknown layout {name!r}. available: {sorted(LAYOUTS)}\n"
            f"適切なレイアウトが無い場合は、既存の組み合わせ（split/compare ブロック）で"
            f"表現できないか検討し、それでも必要なら新パターンとして提案してください。"
        )
    LAYOUTS[name].build(ctx, spec)
    notes = spec.get("speaker_notes") or []
    for note in ([notes] if isinstance(notes, str) else notes):
        ctx.add_speaker_note(str(note))
    if spec.get("references") and name != "closing":
        C.add_reference_note(ctx, spec["references"])


def _head(ctx: SlideCtx, spec: dict) -> Box:
    return C.add_slide_title(
        ctx, spec.get("title", ""), spec.get("lead") or spec.get("key_message"),
        section=spec.get("section"),
    )


def _reserve_footnote(ctx: SlideCtx, body: Box, spec: dict) -> Box:
    """出典行を書く場合、本文領域の下端を空けておく。"""
    if not spec.get("references"):
        return body
    st = ctx.theme.style("note")
    h = pt_to_inches(st.size) * 1.7 * len(spec["references"]) + 0.06
    return Box(body.x, body.y, body.w, max(body.h - h, 0.4))


# --------------------------------------------------------------------------
# 表紙・区切り・目次
# --------------------------------------------------------------------------
@layout(LayoutSpec(
    id="title_cover",
    purpose="表紙",
    description="タイトル／サブタイトル／発表者・所属・日付・場所を左寄せで配置し、細い罫線で区切る",
    suited_for=["発表の表紙"],
    volume="タイトル 1 行＋補足 1 行＋メタ情報 3 行まで",
    functions=["add_slide_title", "shapes.add_hline"],
    cautions=["ロゴ・背景画像は入れない", "装飾を足さない"],
    keys=["title", "subtitle", "author", "affiliation", "date", "event"],
))
def _title_cover(ctx: SlideCtx, spec: dict) -> None:
    theme = ctx.theme
    meta = ctx.deck.meta
    ctx.show_footer = False
    w, h = theme.slide_size_in
    mx = float(theme.lay("margin_x_in", 0.62))
    title = str(spec.get("title") or meta.title)
    subtitle = str(spec.get("subtitle") or meta.subtitle)

    y = h * 0.33
    from ..textmetrics import wrapped_line_count
    title_h = wrapped_line_count(title, theme.style("deck_title").size, w - 2 * mx) * pt_to_inches(theme.style("deck_title").size) * float(theme.lay("line_spacing", 1.22))
    tb = S.new_textbox(ctx.slide, Box(mx, y, w - 2 * mx, title_h), name="deck-title")
    S.write_paragraph(tb.text_frame, theme, title, theme.style("deck_title"),
                      first=True, space_after_pt=0)
    y += max(0.72, title_h + 0.12)
    if subtitle:
        tb = S.new_textbox(ctx.slide, Box(mx, y, w - 2 * mx, 0.5), name="deck-subtitle")
        S.write_paragraph(tb.text_frame, theme, subtitle, theme.style("deck_subtitle"),
                          first=True, space_after_pt=0)
        y += 0.46
    y += 0.12
    S.add_hline(ctx.slide, theme, mx, y, min(3.4, w - 2 * mx), color="accent", weight_pt=2.0,
                name="cover-rule")
    y += 0.26

    lines = [str(x) for x in (
        spec.get("event") or meta.event,
        " ".join(x for x in (str(spec.get("affiliation") or meta.affiliation),
                             str(spec.get("author") or meta.author)) if x),
        spec.get("date") or meta.date,
    ) if x]
    if lines:
        tb = S.new_textbox(ctx.slide, Box(mx, y, w - 2 * mx, 1.2), name="deck-meta")
        for i, line in enumerate(lines):
            S.write_paragraph(tb.text_frame, theme, line, theme.style("deck_meta"),
                              first=(i == 0), space_after_pt=3)


@layout(LayoutSpec(
    id="section_divider",
    purpose="章の区切り",
    description="章番号＋章タイトルを大きく置き、必要なら本章の論点を 1〜3 行添える",
    suited_for=["章の切り替え"],
    volume="タイトル 1 行＋論点 3 項目まで",
    functions=["shapes.add_hline", "add_bullet_list"],
    cautions=["毎章入れると冗長。4 章以上の構成でのみ使う"],
    keys=["title", "number", "items"],
))
def _section_divider(ctx: SlideCtx, spec: dict) -> None:
    theme = ctx.theme
    w, h = theme.slide_size_in
    mx = float(theme.lay("margin_x_in", 0.62))
    ctx.section = str(spec.get("section") or spec.get("title", ""))
    y = h * 0.36
    if spec.get("number") is not None:
        tb = S.new_textbox(ctx.slide, Box(mx, y - 0.42, 2.0, 0.4), name="section-number")
        S.write_paragraph(tb.text_frame, theme, str(spec["number"]),
                          theme.style("section_label"), first=True, space_after_pt=0)
    tb = S.new_textbox(ctx.slide, Box(mx, y, w - 2 * mx, 0.8), name="section-title")
    S.write_paragraph(tb.text_frame, theme, str(spec.get("title", "")),
                      theme.style("deck_title").scaled(0.82), first=True, space_after_pt=0)
    S.add_hline(ctx.slide, theme, mx, y + 0.78, min(3.0, w - 2 * mx), color="accent",
                weight_pt=2.0, name="section-rule")
    if spec.get("items"):
        C.add_bullet_list(ctx, Box(mx, y + 1.0, w - 2 * mx, 1.4), spec["items"], strict=False)


@layout(LayoutSpec(
    id="agenda",
    purpose="目次・発表の流れ",
    description="章を番号付きで縦に並べる。現在地を示す場合は current で強調",
    suited_for=["目次", "発表の構成説明"],
    volume="章 3〜7 件",
    functions=["add_slide_title", "draw_step_list"],
    cautions=["章タイトルは体言止めで短く"],
    keys=["title", "items", "current"],
))
def _agenda(ctx: SlideCtx, spec: dict) -> None:
    body = _head(ctx, spec)
    items = list(spec.get("items") or [])
    current = spec.get("current")
    theme = ctx.theme
    y = body.y
    row_h = min(0.62, body.h / max(len(items), 1))
    for i, item in enumerate(items, start=1):
        text = item if isinstance(item, str) else str(item.get("text", ""))
        is_cur = (current == i) or (isinstance(item, dict) and item.get("current"))
        num_style = theme.style("heading").with_(color="accent" if is_cur else "muted")
        txt_style = theme.style("body").with_(
            bold=bool(is_cur), color="ink" if is_cur else "ink_soft")
        tb = S.new_textbox(ctx.slide, Box(body.x, y, 0.5, row_h), anchor="middle")
        S.write_paragraph(tb.text_frame, theme, f"{i:02d}", num_style, first=True, space_after_pt=0)
        tb = S.new_textbox(ctx.slide, Box(body.x + 0.56, y, body.w - 0.56, row_h), anchor="middle")
        S.write_paragraph(tb.text_frame, theme, text, txt_style, first=True, space_after_pt=0)
        S.add_hline(ctx.slide, theme, body.x, y + row_h, body.w, color="rule_soft", weight_pt=0.75)
        y += row_h


# --------------------------------------------------------------------------
# 本文系
# --------------------------------------------------------------------------
@layout(LayoutSpec(
    id="bullets",
    purpose="箇条書きによる説明",
    description="タイトル＋リード文＋箇条書き（2 階層まで）。必要なら下部に注記ブロック",
    suited_for=["概要説明", "論点整理", "まとめ"],
    volume="第 1 階層 3〜6 件、1 行 40 字以内",
    functions=["add_slide_title", "add_bullet_list", "add_note_block"],
    cautions=["7 件以上は分割する", "全ページこの型が続くと単調になる"],
    keys=["title", "lead", "bullets", "note", "references"],
))
def _bullets(ctx: SlideCtx, spec: dict) -> None:
    body = _reserve_footnote(ctx, _head(ctx, spec), spec)
    blocks: list[Any] = []
    if spec.get("bullets"):
        blocks.append({"type": "bullets", "items": spec["bullets"], "ratio": 3.0})
    if spec.get("body"):
        blocks.append({"type": "text", "text": spec["body"], "ratio": 2.0})
    if spec.get("note"):
        blocks.append({"type": "note", "text": spec["note"], "height_in": 0.0, "ratio": 1.0})
    if not blocks:
        raise DesignRuleError("bullets レイアウトには bullets / body のいずれかが必要です")
    render_stack(ctx, body, blocks)


@layout(LayoutSpec(
    id="text_figure",
    purpose="説明＋図",
    description="左に本文（箇条書き）、右に図・表・グラフ。比率は ratios で調整",
    suited_for=["手法説明", "装置紹介", "結果の説明"],
    volume="左は 3〜5 項目、右は図 1 点",
    functions=["draw_split_layout", "add_bullet_list", "add_image_with_caption", "add_chart"],
    cautions=["図が主役なら figure_text（左右逆）を使う", "図の説明は図の近くに置く"],
    keys=["title", "lead", "left", "right", "ratios"],
))
def _text_figure(ctx: SlideCtx, spec: dict) -> None:
    body = _reserve_footnote(ctx, _head(ctx, spec), spec)
    ratios = spec.get("ratios") or (1.0, 1.15)
    left, right = D.draw_split_layout(
        ctx, body, ratios=ratios,
        headings=spec.get("headings"), divider=bool(spec.get("divider", False)),
    )
    render_block(ctx, left, spec.get("left") or
                 {"type": "bullets", "items": spec.get("bullets") or []})
    render_block(ctx, right, spec.get("right") or spec.get("figure") or
                 {"type": "figure", "label": "図を配置"})


@layout(LayoutSpec(
    id="figure_text",
    purpose="図＋説明（図が主役）",
    description="左に図、右に短い説明。図を大きく見せたい場合に使う",
    suited_for=["システム外観", "実験セットアップ", "結果グラフ"],
    volume="右の説明は 3 項目以内",
    functions=["draw_split_layout", "add_image_with_caption", "add_bullet_list"],
    cautions=["説明が 5 項目以上なら text_figure にする"],
    keys=["title", "lead", "left", "right", "ratios"],
))
def _figure_text(ctx: SlideCtx, spec: dict) -> None:
    body = _reserve_footnote(ctx, _head(ctx, spec), spec)
    ratios = spec.get("ratios") or (1.35, 1.0)
    left, right = D.draw_split_layout(ctx, body, ratios=ratios,
                                      headings=spec.get("headings"))
    render_block(ctx, left, spec.get("left") or spec.get("figure") or
                 {"type": "figure", "label": "図を配置"})
    render_block(ctx, right, spec.get("right") or
                 {"type": "bullets", "items": spec.get("bullets") or []})


@layout(LayoutSpec(
    id="two_column",
    purpose="2 段組の自由配置",
    description="左右に任意のブロックを置く汎用レイアウト（ブロックは縦積みも可）",
    suited_for=["表＋グラフ", "図＋表", "説明＋数式"],
    volume="片側 2 ブロックまで",
    functions=["draw_split_layout", "render_block"],
    cautions=["片側に 3 ブロック以上積むと読みにくい"],
    keys=["title", "lead", "left", "right", "ratios", "headings"],
))
def _two_column(ctx: SlideCtx, spec: dict) -> None:
    body = _reserve_footnote(ctx, _head(ctx, spec), spec)
    left, right = D.draw_split_layout(
        ctx, body, ratios=spec.get("ratios") or (1, 1),
        headings=spec.get("headings"), divider=bool(spec.get("divider", False)),
    )
    render_block(ctx, left, spec.get("left"))
    render_block(ctx, right, spec.get("right"))


@layout(LayoutSpec(
    id="comparison",
    purpose="左右比較",
    description="2〜3 列に見出し帯を付けて並べ、同じ観点で比較する",
    suited_for=["従来手法と提案手法", "案の比較", "導入前後"],
    volume="列ごとに 3〜5 項目",
    functions=["draw_comparison_layout"],
    cautions=["列ごとに項目数と観点の順序を揃える", "優劣は色ではなく記述で示す"],
    keys=["title", "lead", "columns", "ratios"],
))
def _comparison(ctx: SlideCtx, spec: dict) -> None:
    body = _reserve_footnote(ctx, _head(ctx, spec), spec)
    columns = spec.get("columns") or []
    if len(columns) < 2:
        raise DesignRuleError("comparison レイアウトには columns が 2 つ以上必要です")
    D.draw_comparison_layout(ctx, body, columns, ratios=spec.get("ratios"))


@layout(LayoutSpec(
    id="problem_solution",
    purpose="課題と解決策",
    description="上段に課題、下段に解決策（または左右）。間を矢印でつなぐ",
    suited_for=["提案の動機", "改善提案"],
    volume="課題 2〜4 件、解決策 2〜4 件",
    functions=["draw_split_layout", "add_bullet_list", "shapes.add_connector"],
    cautions=["課題と解決策を 1 対 1 で対応させる", "矢印を増やしすぎない"],
    keys=["title", "lead", "problem", "solution", "direction"],
))
def _problem_solution(ctx: SlideCtx, spec: dict) -> None:
    theme = ctx.theme
    body = _reserve_footnote(ctx, _head(ctx, spec), spec)
    problem = spec.get("problem") or {}
    solution = spec.get("solution") or {}
    direction = spec.get("direction", "h")
    p_title = str(problem.get("title", "課題"))
    s_title = str(solution.get("title", "解決策"))
    if direction == "h":
        gap = 0.62
        cols = body.split_h(ratios=[1, 1], gap=gap)
        D.draw_comparison_layout(
            ctx, body,
            [{"title": p_title, "tone": "surface", **_content_only(problem)},
             {"title": s_title, "tone": "accent_pale", **_content_only(solution)}],
            gap=gap,
        )
        mid_x = (cols[0].right + cols[1].x) / 2
        S.add_connector(ctx.slide, theme, (mid_x - 0.16, body.cy), (mid_x + 0.16, body.cy),
                        kind="straight", color="accent", weight_pt=2.0, name="ps-arrow")
    else:
        top, bottom = body.split_v(ratios=[1, 1], gap=0.56)
        D.draw_comparison_layout(ctx, top, [{"title": p_title, "tone": "surface",
                                             **_content_only(problem)}], gap=0)
        D.draw_comparison_layout(ctx, bottom, [{"title": s_title, "tone": "accent_pale",
                                                **_content_only(solution)}], gap=0)
        S.add_connector(ctx.slide, theme, (body.cx, top.bottom + 0.08),
                        (body.cx, bottom.y - 0.08), kind="straight", color="accent",
                        weight_pt=2.0, name="ps-arrow")


def _content_only(spec: dict) -> dict:
    return {k: v for k, v in spec.items() if k in ("items", "text")}


# --------------------------------------------------------------------------
# 図解系
# --------------------------------------------------------------------------
@layout(LayoutSpec(
    id="process_flow",
    purpose="処理フロー",
    description="処理の順序を矩形＋矢印で示し、必要なら各段の補足を下に書く",
    suited_for=["処理手順", "実験手順", "データの流れ"],
    volume="3〜6 段。各段のラベルは 12 字以内",
    functions=["draw_process_flow", "add_note_block"],
    cautions=["意味の薄い 3 段フローを作らない", "分岐がある場合は diagram を使う"],
    keys=["title", "lead", "steps", "direction", "note"],
))
def _process_flow(ctx: SlideCtx, spec: dict) -> None:
    body = _reserve_footnote(ctx, _head(ctx, spec), spec)
    blocks: list[Any] = [{"type": "flow", "steps": spec.get("steps") or [],
                          "direction": spec.get("direction", "h"),
                          "numbered": spec.get("numbered", True), "ratio": 3.0}]
    if spec.get("note"):
        blocks.append({"type": "note", "text": spec["note"], "ratio": 1.0})
    if spec.get("bullets"):
        blocks.append({"type": "bullets", "items": spec["bullets"], "ratio": 1.4})
    render_stack(ctx, body, blocks)


@layout(LayoutSpec(
    id="system_diagram",
    purpose="システム構成図",
    description="グリッド上にノードを置き、コネクタで接続する。グループ枠で括れる",
    suited_for=["システム構成", "ハードウェア構成", "ソフトウェア構成"],
    volume="ノード 4〜9 個、エッジ 8 本以内",
    functions=["draw_system_diagram", "add_note_block"],
    cautions=["ノードの大きさは意味に対応させる", "交差するエッジを増やさない"],
    keys=["title", "lead", "nodes", "edges", "groups", "rows", "cols", "note"],
))
def _system_diagram(ctx: SlideCtx, spec: dict) -> None:
    body = _reserve_footnote(ctx, _head(ctx, spec), spec)
    blocks: list[Any] = [{"type": "diagram", "nodes": spec.get("nodes") or [],
                          "edges": spec.get("edges") or [], "groups": spec.get("groups") or [],
                          "rows": spec.get("rows"), "cols": spec.get("cols"), "ratio": 3.2}]
    if spec.get("note"):
        blocks.append({"type": "note", "text": spec["note"], "ratio": 1.0})
    render_stack(ctx, body, blocks)


@layout(LayoutSpec(
    id="algorithm",
    purpose="アルゴリズム説明",
    description="左に手順（番号付き）、右に数式・擬似コード・図",
    suited_for=["アルゴリズム", "制御則", "処理の定式化"],
    volume="手順 3〜6、数式 2 本まで",
    functions=["draw_step_list", "add_formula", "draw_split_layout"],
    cautions=["記号は必ず定義する", "式番号は参照する場合だけ付ける"],
    keys=["title", "lead", "steps", "right", "formulas", "ratios"],
))
def _algorithm(ctx: SlideCtx, spec: dict) -> None:
    body = _reserve_footnote(ctx, _head(ctx, spec), spec)
    left, right = D.draw_split_layout(ctx, body, ratios=spec.get("ratios") or (1.1, 1.0),
                                      headings=spec.get("headings"))
    D.draw_step_list(ctx, left, spec.get("steps") or [])
    rblock = spec.get("right")
    if rblock is None and spec.get("formulas"):
        rblock = [{"type": "formula", "text": f.get("text", f) if isinstance(f, dict) else f,
                   "number": (f.get("number", "") if isinstance(f, dict) else "")}
                  for f in spec["formulas"]]
    render_block(ctx, right, rblock or {"type": "figure", "label": "式・図を配置"})


@layout(LayoutSpec(
    id="timeline",
    purpose="時系列",
    description="横軸 1 本に出来事を並べる。ラベルは上下交互",
    suited_for=["経緯", "開発の流れ", "検討の推移"],
    volume="3〜6 点",
    functions=["draw_timeline"],
    cautions=["等間隔が実時間と異なる場合は注記する"],
    keys=["title", "lead", "milestones", "note"],
))
def _timeline(ctx: SlideCtx, spec: dict) -> None:
    body = _reserve_footnote(ctx, _head(ctx, spec), spec)
    blocks: list[Any] = [{"type": "timeline", "milestones": spec.get("milestones") or [],
                          "axis_label": spec.get("axis_label", ""), "ratio": 3.0}]
    if spec.get("note"):
        blocks.append({"type": "note", "text": spec["note"], "ratio": 1.0})
    render_stack(ctx, body, blocks)


@layout(LayoutSpec(
    id="roadmap",
    purpose="ロードマップ",
    description="レーン × 期間のバーで計画を示す",
    suited_for=["開発計画", "検討スケジュール"],
    volume="レーン 2〜5、期間 3〜6",
    functions=["draw_roadmap"],
    cautions=["確定していない期間は点線や注記で区別する"],
    keys=["title", "lead", "periods", "lanes", "bars", "note"],
))
def _roadmap(ctx: SlideCtx, spec: dict) -> None:
    body = _reserve_footnote(ctx, _head(ctx, spec), spec)
    blocks: list[Any] = [{"type": "roadmap", "periods": spec.get("periods") or [],
                          "lanes": spec.get("lanes") or [], "bars": spec.get("bars") or [],
                          "ratio": 3.0}]
    if spec.get("note"):
        blocks.append({"type": "note", "text": spec["note"], "ratio": 1.0})
    render_stack(ctx, body, blocks)


# --------------------------------------------------------------------------
# 実験・結果系
# --------------------------------------------------------------------------
@layout(LayoutSpec(
    id="experiment_setup",
    purpose="実験条件・セットアップ",
    description="左に条件表、右に装置写真・構成図",
    suited_for=["実験条件", "評価環境", "計測系"],
    volume="条件 4〜8 行",
    functions=["make_table", "add_image_with_caption", "draw_split_layout"],
    cautions=["単位を必ず書く", "未確定の条件は空欄にして捏造しない"],
    keys=["title", "lead", "conditions", "figure", "ratios", "note"],
))
def _experiment_setup(ctx: SlideCtx, spec: dict) -> None:
    body = _reserve_footnote(ctx, _head(ctx, spec), spec)
    left, right = D.draw_split_layout(ctx, body, ratios=spec.get("ratios") or (1.1, 1.0),
                                      headings=spec.get("headings"))
    cond = spec.get("conditions")
    if isinstance(cond, dict):
        left_block = cond
    elif isinstance(cond, list):
        left_block = {"type": "table", "header": ["項目", "条件"],
                      "rows": [[k, v] for k, v in (
                          (c if isinstance(c, (list, tuple)) else (c.get("item"), c.get("value")))
                          for c in cond)],
                      "col_ratios": [1.0, 1.4], "align": ["left", "left"]}
    else:
        left_block = spec.get("left")
    render_block(ctx, left, left_block)
    render_block(ctx, right, spec.get("figure") or spec.get("right") or
                 {"type": "figure", "label": "実験セットアップ写真"})


@layout(LayoutSpec(
    id="results_chart",
    purpose="実験結果（グラフ）",
    description="左にグラフ、右に読み取れること（箇条書き）。逆配置も可",
    suited_for=["評価結果", "比較実験", "計測結果"],
    volume="グラフ 1 点＋所見 2〜4 件",
    functions=["add_chart", "add_bullet_list", "draw_split_layout"],
    cautions=["軸ラベルと単位を必ず入れる", "与えられていない数値を作らない"],
    keys=["title", "lead", "chart", "findings", "ratios", "mirror", "note"],
))
def _results_chart(ctx: SlideCtx, spec: dict) -> None:
    body = _reserve_footnote(ctx, _head(ctx, spec), spec)
    ratios = spec.get("ratios") or (1.3, 1.0)
    chart_block = spec.get("chart") or {"type": "figure", "label": "グラフを配置"}
    if isinstance(chart_block, dict) and "type" not in chart_block:
        chart_block = {"type": "chart", **chart_block}
    findings = spec.get("findings") or spec.get("bullets") or []
    side_blocks: list[Any] = []
    if findings:
        side_blocks.append({"type": "bullets", "items": findings, "ratio": 3.0,
                            "heading": spec.get("findings_heading", "読み取れること")})
    if spec.get("note"):
        side_blocks.append({"type": "note", "text": spec["note"], "ratio": 1.0})
    if spec.get("mirror"):
        left, right = D.draw_split_layout(ctx, body, ratios=list(reversed(list(ratios))))
        render_block(ctx, left, side_blocks or None)
        render_block(ctx, right, chart_block)
    else:
        left, right = D.draw_split_layout(ctx, body, ratios=ratios)
        render_block(ctx, left, chart_block)
        render_block(ctx, right, side_blocks or None)


@layout(LayoutSpec(
    id="table",
    purpose="表による整理",
    description="1 枚の中心に表を置く。上に前提、下に注記を添えられる",
    suited_for=["仕様一覧", "条件整理", "結果の数値一覧"],
    volume="7 行 × 5 列程度まで",
    functions=["make_table", "add_note_block"],
    cautions=["行が多い場合は分割か抜粋にする", "セル内で改行を多用しない"],
    keys=["title", "lead", "table", "note"],
))
def _table(ctx: SlideCtx, spec: dict) -> None:
    body = _reserve_footnote(ctx, _head(ctx, spec), spec)
    tbl = spec.get("table") or {}
    if "type" not in tbl:
        tbl = {"type": "table", **tbl}
    blocks: list[Any] = [{**tbl, "ratio": 3.0}]
    if spec.get("note"):
        blocks.append({"type": "note", "text": spec["note"], "ratio": 1.0})
    render_stack(ctx, body, blocks)


@layout(LayoutSpec(
    id="evaluation_matrix",
    purpose="定性評価マトリクス",
    description="対象 × 評価軸の記号評価（◎○△×）と所見列",
    suited_for=["方式比較", "候補の絞り込み"],
    volume="対象 3〜5、評価軸 3〜5",
    functions=["make_matrix"],
    cautions=["記号の定義を注記する", "根拠の無い評価を付けない"],
    keys=["title", "lead", "options", "criteria", "ratings", "comments", "note"],
))
def _evaluation_matrix(ctx: SlideCtx, spec: dict) -> None:
    body = _reserve_footnote(ctx, _head(ctx, spec), spec)
    blocks: list[Any] = [{"type": "matrix", "options": spec.get("options") or [],
                          "criteria": spec.get("criteria") or [],
                          "ratings": spec.get("ratings") or [],
                          "comments": spec.get("comments"),
                          "caption": spec.get("caption", ""), "ratio": 3.0}]
    note = spec.get("note") or "◎: 優れる／○: 良／△: 課題あり／×: 不適"
    blocks.append({"type": "note", "text": note, "ratio": 1.0})
    render_stack(ctx, body, blocks)


@layout(LayoutSpec(
    id="image_focus",
    purpose="図・写真を主役にする",
    description="1 枚の図を大きく置き、下にキャプションと短い説明",
    suited_for=["装置写真", "画面例", "大きな構成図"],
    volume="図 1 点＋説明 2 行まで",
    functions=["add_image_with_caption", "add_body_text"],
    cautions=["図の中の文字が 10pt 相当未満にならないようにする"],
    keys=["title", "lead", "image", "caption", "note"],
))
def _image_focus(ctx: SlideCtx, spec: dict) -> None:
    body = _reserve_footnote(ctx, _head(ctx, spec), spec)
    blocks: list[Any] = []
    img = spec.get("image")
    if img:
        blocks.append({"type": "image", "image": img, "caption": spec.get("caption", ""),
                       "ratio": 4.0})
    else:
        blocks.append({"type": "figure", "label": spec.get("caption") or "図を配置",
                       "ratio": 4.0})
    if spec.get("note"):
        blocks.append({"type": "note", "text": spec["note"], "ratio": 1.0})
    render_stack(ctx, body, blocks)


@layout(LayoutSpec(
    id="summary",
    purpose="まとめ",
    description="要点を番号付きで示し、最後に次の一手（任意）",
    suited_for=["まとめ", "結論", "今後の予定"],
    volume="要点 3〜4 件",
    functions=["draw_step_list", "add_key_message", "add_bullet_list"],
    cautions=["本文の繰り返しではなく、結論を書く"],
    keys=["title", "lead", "points", "next_steps"],
))
def _summary(ctx: SlideCtx, spec: dict) -> None:
    body = _reserve_footnote(ctx, _head(ctx, spec), spec)
    blocks: list[Any] = []
    if spec.get("points"):
        blocks.append({"type": "steps", "steps": spec["points"], "ratio": 3.0})
    if spec.get("next_steps"):
        blocks.append({"type": "bullets", "items": spec["next_steps"], "ratio": 1.6,
                       "heading": spec.get("next_heading", "今後の予定")})
    if not blocks:
        raise DesignRuleError("summary レイアウトには points が必要です")
    render_stack(ctx, body, blocks)


@layout(LayoutSpec(
    id="closing",
    purpose="結び・参考文献",
    description="短い結びの言葉と、参考文献・連絡先",
    suited_for=["最終ページ", "参考文献一覧"],
    volume="文献 6 件まで",
    functions=["add_slide_title", "add_bullet_list", "add_reference_note"],
    cautions=["装飾的な「ご清聴ありがとうございました」だけのページは避ける"],
    keys=["title", "message", "references", "contact"],
))
def _closing(ctx: SlideCtx, spec: dict) -> None:
    theme = ctx.theme
    body = _head(ctx, spec)
    y = body.y
    if spec.get("message"):
        used = C.add_key_message(ctx, Box(body.x, y, body.w, 0.6), str(spec["message"]))
        y += used.h + 0.3
    refs = spec.get("references") or []
    if refs:
        used = C.add_section_heading(ctx, Box(body.x, y, body.w, 0.4),
                                     spec.get("references_heading", "参考文献"))
        y += used.h + 0.08
        items = [r if isinstance(r, str) else str(r.get("text", "")) for r in refs]
        bracket = theme.conventions.get("reference_style") == "bracket"
        lines = [f"[{i}] {t}" if bracket and not t.startswith("[") else t
                 for i, t in enumerate(items, start=1)]
        C.add_body_text(ctx, Box(body.x, y, body.w, body.bottom - y - 0.4), lines,
                        style="note", strict=False)
    if spec.get("contact"):
        C.add_caption(ctx, Box(body.x, body.bottom - 0.32, body.w, 0.3),
                      str(spec["contact"]), align="left")


@layout(LayoutSpec(
    id="free",
    purpose="自由配置（ブロック指定）",
    description="本文領域を縦に積むだけの汎用レイアウト。既存レイアウトで表せない構成に使う",
    suited_for=["特殊な構成", "複合ブロック"],
    volume="ブロック 3 つまで",
    functions=["render_stack"],
    cautions=["多用するとレイアウトの一貫性が崩れる。頻出するなら新レイアウトとして提案する"],
    keys=["title", "lead", "blocks"],
))
def _free(ctx: SlideCtx, spec: dict) -> None:
    body = _reserve_footnote(ctx, _head(ctx, spec), spec)
    render_stack(ctx, body, list(spec.get("blocks") or []))


@layout(LayoutSpec(
    id="custom_script",
    purpose="1 スライド＝1 ビルドスクリプト",
    description="Python スクリプトの build(ctx, spec) を呼ぶ逃げ道。複雑な作図に使う",
    suited_for=["どうしても手で座標を決めたい図"],
    volume="—",
    functions=["（任意）"],
    cautions=["テーマのヘルパ関数を使うこと。生の座標指定でデザイン規則を破らない"],
    keys=["title", "script"],
))
def _custom_script(ctx: SlideCtx, spec: dict) -> None:
    import importlib.util
    from pathlib import Path

    path = Path(str(spec.get("script", ""))).expanduser()
    if not path.exists():
        raise DesignRuleError(f"custom_script: スクリプトが見つかりません: {path}")
    mod_spec = importlib.util.spec_from_file_location(f"structured_slide_creator_custom_{path.stem}", path)
    module = importlib.util.module_from_spec(mod_spec)
    mod_spec.loader.exec_module(module)
    if not hasattr(module, "build"):
        raise DesignRuleError(f"custom_script: {path} に build(ctx, spec) がありません")
    module.build(ctx, spec)


def catalog_entries() -> list[dict]:
    """レイアウトカタログ（組み込み分）を辞書で返す。"""
    out = []
    for spec in LAYOUTS.values():
        out.append({
            "id": spec.id,
            "purpose": spec.purpose,
            "description": spec.description,
            "suited_for": spec.suited_for,
            "volume": spec.volume,
            "functions": spec.functions,
            "cautions": spec.cautions,
            "keys": spec.keys,
            "source": "builtin",
            "status": "accepted",
        })
    return out

"""レイアウト骨格と図解（分割・比較・フロー・構成図・ロードマップ）。

いずれも **編集可能なネイティブ図形とコネクタ** で構成する。
関数は「描いた領域」または「領域の並び」を返し、呼び出し側は座標を自分で計算しない。
"""

from __future__ import annotations

from typing import Any, Sequence

from pptx.enum.shapes import MSO_SHAPE

from ..design.rules import DesignRuleError, check_limit
from ..textmetrics import measure, wrapped_line_count
from ..units import Box, pt_to_inches
from . import shapes as S
from .components import add_bullet_list, add_body_text, add_caption, add_section_heading
from .deck import SlideCtx

NODE_KINDS = {
    # kind: (fill, line, line_weight, dash, bold)
    "box": ("bg", "rule", 1.0, None, False),
    "emphasis": ("accent_pale", "accent", 1.5, None, True),
    "io": ("bg", "muted", 1.0, "dash", False),
    "store": ("surface", "rule", 1.0, None, False),
    "external": ("surface_2", "muted", 1.0, "dash", False),
    "group": ("surface", "rule_soft", 1.0, None, False),
}


# --------------------------------------------------------------------------
# 骨格レイアウト
# --------------------------------------------------------------------------
def draw_split_layout(
    ctx: SlideCtx,
    box: Box,
    *,
    ratios: Sequence[float] = (1, 1),
    headings: Sequence[str] | None = None,
    divider: bool = False,
    gap: float | None = None,
) -> list[Box]:
    """左右（または 3 列）分割。見出しを付けた場合は、その下の本文領域を返す。"""
    theme = ctx.theme
    gap = float(theme.lay("gutter_in", 0.32)) if gap is None else gap
    cols = box.split_h(ratios=list(ratios), gap=gap)
    if divider and len(cols) > 1:
        for left, right in zip(cols, cols[1:]):
            x = (left.right + right.x) / 2
            S.add_vline(ctx.slide, theme, x, box.y + 0.04, box.h - 0.08,
                        color="rule_soft", weight_pt=0.75, name="split-divider")
    out: list[Box] = []
    for i, col in enumerate(cols):
        if headings and i < len(headings) and headings[i]:
            used = add_section_heading(ctx, col, headings[i])
            out.append(Box(col.x, col.y + used.h + 0.06, col.w, col.h - used.h - 0.06))
        else:
            out.append(col)
    return out


def draw_comparison_layout(
    ctx: SlideCtx,
    box: Box,
    columns: Sequence[dict],
    *,
    ratios: Sequence[float] | None = None,
    gap: float | None = None,
    band: bool = True,
) -> list[Box]:
    """比較列。各列に見出し帯を置き、本文領域を返す。

    columns: [{"title": "従来手法", "tone": "surface"|"accent_pale", "items": [...] }, ...]
    items / text を与えた場合はこの関数が中身も書く。
    """
    theme = ctx.theme
    gap = float(theme.lay("gutter_in", 0.32)) if gap is None else gap
    ratios = list(ratios) if ratios else [1.0] * len(columns)
    cols = box.split_h(ratios=ratios, gap=gap)
    bodies: list[Box] = []
    head_style = theme.style("heading")
    band_h = pt_to_inches(head_style.size) * 1.9
    for spec, col in zip(columns, cols):
        title = str(spec.get("title", ""))
        tone = spec.get("tone", "surface")
        if title and band:
            shp = S.add_rect(ctx.slide, theme, Box(col.x, col.y, col.w, band_h),
                             fill=tone, line=None, name="compare-band")
            color = "accent" if tone != "accent" else "on_accent"
            S.fill_shape_text(shp, theme, title, head_style.with_(color=color), align="center")
            body = Box(col.x, col.y + band_h + 0.10, col.w, col.h - band_h - 0.10)
        elif title:
            used = add_section_heading(ctx, col, title)
            body = Box(col.x, col.y + used.h + 0.06, col.w, col.h - used.h - 0.06)
        else:
            body = col
        if spec.get("items"):
            add_bullet_list(ctx, body.inset(0.06, 0.0), spec["items"], strict=False)
        elif spec.get("text"):
            add_body_text(ctx, body.inset(0.06, 0.0), spec["text"], strict=False)
        bodies.append(body)
    return bodies


# --------------------------------------------------------------------------
# フロー図
# --------------------------------------------------------------------------
def draw_process_flow(
    ctx: SlideCtx,
    box: Box,
    steps: Sequence[Any],
    *,
    direction: str = "h",
    numbered: bool = True,
    kind: str = "box",
    detail_below: bool = True,
) -> list:
    """処理フロー。矩形ノード＋矢印コネクタ（グラデーションや影は使わない）。

    steps: ["検出", ...] または [{"label":…, "detail":…, "kind":"emphasis"}, ...]
    戻り値: 生成したノード図形の一覧（後からの接続・加工に使える）
    """
    theme = ctx.theme
    norm = [{"label": s} if isinstance(s, str) else dict(s) for s in steps]
    if not norm:
        raise DesignRuleError("draw_process_flow: steps が空です")
    check_limit(theme, "max_flow_steps", len(norm), label="フローの段数", hard=False)

    label_style = theme.style("diagram_label")
    shapes_out = []

    if direction == "h":
        arrow = 0.30
        n = len(norm)
        node_w = (box.w - arrow * (n - 1)) / n
        detail_h = 0.0
        if detail_below and any(s.get("detail") for s in norm):
            detail_h = min(0.9, box.h * 0.34)
        node_h = min(box.h - detail_h, max(0.62, box.h * 0.46))
        y = box.y + (box.h - detail_h - node_h) / 2
        prev = None
        for i, s in enumerate(norm):
            x = box.x + i * (node_w + arrow)
            nbox = Box(x, y, node_w, node_h)
            node = _draw_node(ctx, nbox, s, label_style, numbered=numbered, index=i + 1,
                              kind=s.get("kind", kind))
            shapes_out.append(node)
            if prev is not None:
                cxn = S.add_connector(
                    ctx.slide, theme,
                    (x - arrow + 0.04, y + node_h / 2), (x - 0.04, y + node_h / 2),
                    kind="straight", color="accent_2", weight_pt=1.5, name=f"flow-arrow-{i}",
                )
                S.connect(cxn, prev, node, begin_site=3, end_site=1)
            prev = node
            if detail_h and s.get("detail"):
                add_body_text(ctx, Box(x, y + node_h + 0.08, node_w, detail_h - 0.08),
                              str(s["detail"]), style="diagram_note", strict=False)
        return shapes_out

    # 縦フロー
    arrow = 0.26
    n = len(norm)
    node_h = (box.h - arrow * (n - 1)) / n
    prev = None
    for i, s in enumerate(norm):
        y = box.y + i * (node_h + arrow)
        label_w = box.w if not s.get("detail") else box.w * 0.42
        nbox = Box(box.x, y, label_w, node_h)
        node = _draw_node(ctx, nbox, s, label_style, numbered=numbered, index=i + 1,
                          kind=s.get("kind", kind))
        shapes_out.append(node)
        if prev is not None:
            cxn = S.add_connector(
                ctx.slide, theme,
                (box.x + label_w / 2, y - arrow + 0.03), (box.x + label_w / 2, y - 0.03),
                kind="straight", color="accent_2", weight_pt=1.5, name=f"flow-arrow-{i}",
            )
            S.connect(cxn, prev, node, begin_site=2, end_site=0)
        prev = node
        if s.get("detail"):
            add_body_text(ctx, Box(box.x + label_w + 0.2, y + 0.02, box.w - label_w - 0.2,
                                   node_h - 0.04),
                          str(s["detail"]), style="diagram_note", strict=False)
    return shapes_out


def _draw_node(ctx: SlideCtx, nbox: Box, spec: dict, label_style, *,
               numbered: bool = False, index: int = 0, kind: str = "box"):
    theme = ctx.theme
    fill, line, weight, dash, bold = NODE_KINDS.get(kind, NODE_KINDS["box"])
    shp = S.add_rect(ctx.slide, theme, nbox, fill=fill, line=line, line_weight_pt=weight,
                     dash=dash, name=f"node-{spec.get('id', index)}")
    label = str(spec.get("label", ""))
    if numbered and index:
        label = f"{index}. {label}"
    S.fill_shape_text(shp, theme, label, label_style.with_(bold=bold or label_style.bold))
    return shp


def draw_step_list(
    ctx: SlideCtx,
    box: Box,
    steps: Sequence[Any],
    *,
    gap: float = 0.10,
) -> Box:
    """番号付きの手順リスト（アルゴリズム説明向け）。

    左に番号、右に本文。箱で囲まないので情報密度を上げられる。
    """
    theme = ctx.theme
    norm = [{"label": s} if isinstance(s, str) else dict(s) for s in steps]
    num_w = 0.34
    body_style = theme.style("body")
    note_style = theme.style("diagram_note")
    text_w = box.w - num_w
    # add_body_text と同じ条件で見積もる（段落後の空きを含める）
    space_after = float(theme.lay("para_space_after_pt", 5))
    rows: list[tuple[float, float]] = []   # (label_h, detail_h)
    for s in norm:
        label_h = max(
            measure(theme, [(str(s.get("label", "")), body_style.size)],
                    text_w, space_after_pt=space_after),
            pt_to_inches(body_style.size) * 1.45,
        )
        detail_h = 0.0
        if s.get("detail"):
            detail_h = measure(theme, [(str(s["detail"]), note_style.size)],
                               text_w, space_after_pt=space_after) + 0.02
        rows.append((label_h, detail_h))
    heights = [a + b for a, b in rows]
    total = sum(heights) + gap * (len(norm) - 1)
    if total > box.h * 1.12:
        raise DesignRuleError(
            f"draw_step_list: 手順が領域に収まりません（必要 {total:.2f}in / 枠 {box.h:.2f}in）。"
            f" 手順をまとめるか、2 枚に分割してください。"
        )
    y = box.y
    for i, (s, (label_h, detail_h)) in enumerate(zip(norm, rows), start=1):
        tb = S.new_textbox(ctx.slide, Box(box.x, y, num_w, label_h), name=f"step-num-{i}")
        S.write_paragraph(tb.text_frame, theme, f"{i}", theme.style("heading"),
                          first=True, align="left", space_after_pt=0)
        add_body_text(ctx, Box(box.x + num_w, y, text_w, label_h),
                      [str(s.get("label", ""))], strict=False)
        if detail_h:
            add_body_text(
                ctx,
                Box(box.x + num_w, y + label_h, text_w, detail_h),
                [str(s["detail"])], style="diagram_note", strict=False,
            )
        y += label_h + detail_h + gap
    return box.with_h(min(total, box.h))


# --------------------------------------------------------------------------
# システム構成図
# --------------------------------------------------------------------------
def draw_system_diagram(
    ctx: SlideCtx,
    box: Box,
    nodes: Sequence[dict],
    edges: Sequence[dict] = (),
    *,
    rows: int | None = None,
    cols: int | None = None,
    gap_x: float = 0.26,
    gap_y: float = 0.24,
    groups: Sequence[dict] = (),
) -> dict:
    """グリッド配置のシステム構成図。

    nodes: [{"id":"ctrl", "label":"制御PC", "row":0, "col":1,
             "row_span":1, "col_span":1, "kind":"box|emphasis|io|store|external"}]
    edges: [{"from":"ctrl", "to":"arm", "label":"EtherCAT", "kind":"elbow|straight",
             "dash":"dash", "arrow":true, "both":false}]
    groups: [{"label":"ロボットセル", "rows":[1,2], "cols":[0,2]}]  # 背景の括り
    戻り値: {node_id: shape}
    """
    theme = ctx.theme
    if not nodes:
        raise DesignRuleError("draw_system_diagram: nodes が空です")
    if groups:
        # Group heading and outer stroke stay inside the allocated content region.
        box = Box(box.x + .10, box.y + .26, box.w - .20, box.h - .36)
    rows = rows or (max(int(n.get("row", 0)) + int(n.get("row_span", 1)) for n in nodes))
    cols = cols or (max(int(n.get("col", 0)) + int(n.get("col_span", 1)) for n in nodes))
    cell_w = (box.w - gap_x * (cols - 1)) / cols
    cell_h = (box.h - gap_y * (rows - 1)) / rows

    def cell_box(r: int, c: int, rs: int = 1, cs: int = 1) -> Box:
        return Box(
            box.x + c * (cell_w + gap_x),
            box.y + r * (cell_h + gap_y),
            cell_w * cs + gap_x * (cs - 1),
            cell_h * rs + gap_y * (rs - 1),
        )

    # 先に group の背景を描く（下に敷く）
    for g in groups:
        rs = list(g.get("rows", [0, rows - 1]))
        cs = list(g.get("cols", [0, cols - 1]))
        gbox = Box(
            cell_box(rs[0], cs[0]).x - 0.10,
            cell_box(rs[0], cs[0]).y - 0.26,
            cell_box(rs[-1], cs[-1]).right - cell_box(rs[0], cs[0]).x + 0.20,
            cell_box(rs[-1], cs[-1]).bottom - cell_box(rs[0], cs[0]).y + 0.36,
        )
        S.add_rect(ctx.slide, theme, gbox, fill="surface", line="rule_soft",
                   dash="dash", name=f"group-{g.get('label', '')}")
        if g.get("label"):
            tb = S.new_textbox(ctx.slide, Box(gbox.x + 0.08, gbox.y + 0.04, gbox.w - 0.16, 0.22))
            S.write_paragraph(tb.text_frame, theme, str(g["label"]),
                              theme.style("diagram_note").with_(bold=True),
                              first=True, space_after_pt=0)

    label_style = theme.style("diagram_label")
    made: dict[str, Any] = {}
    for n in nodes:
        nbox = cell_box(int(n.get("row", 0)), int(n.get("col", 0)),
                        int(n.get("row_span", 1)), int(n.get("col_span", 1)))
        kind = n.get("kind", "box")
        fill, line, weight, dash, bold = NODE_KINDS.get(kind, NODE_KINDS["box"])
        shp = S.add_rect(ctx.slide, theme, nbox, fill=fill, line=line, line_weight_pt=weight,
                         dash=dash, shape_type=MSO_SHAPE.RECTANGLE,
                         name=f"node-{n.get('id', n.get('label', ''))}")
        S.fill_shape_text(shp, theme, str(n.get("label", "")),
                          label_style.with_(bold=bold or label_style.bold))
        if n.get("note"):
            add_caption(ctx, Box(nbox.x, nbox.bottom + 0.02, nbox.w, 0.22), str(n["note"]),
                        align="center")
        made[str(n.get("id", n.get("label", "")))] = shp

    for e in edges:
        a, b = made.get(str(e.get("from"))), made.get(str(e.get("to")))
        if a is None or b is None:
            ctx.deck.warnings.append(
                f"[{ctx.slide_id}] system diagram: 未定義ノードへのエッジ {e}"
            )
            continue
        _connect_shapes(ctx, a, b, e)
        if e.get("label"):
            _edge_label(ctx, a, b, str(e["label"]))
    return made


def _shape_box(shape) -> Box:
    from ..units import EMU_PER_INCH

    return Box(shape.left / EMU_PER_INCH, shape.top / EMU_PER_INCH,
               shape.width / EMU_PER_INCH, shape.height / EMU_PER_INCH)


def _connect_shapes(ctx: SlideCtx, a, b, spec: dict):
    theme = ctx.theme
    ba, bb = _shape_box(a), _shape_box(b)
    horizontal = abs(ba.cy - bb.cy) < max(ba.h, bb.h) * 0.6
    if horizontal:
        if ba.cx <= bb.cx:
            start, end, sites = (ba.right, ba.cy), (bb.x, bb.cy), (3, 1)
        else:
            start, end, sites = (ba.x, ba.cy), (bb.right, bb.cy), (1, 3)
    else:
        if ba.cy <= bb.cy:
            start, end, sites = (ba.cx, ba.bottom), (bb.cx, bb.y), (2, 0)
        else:
            start, end, sites = (ba.cx, ba.y), (bb.cx, bb.bottom), (0, 2)
    cxn = S.add_connector(
        ctx.slide, theme, start, end,
        kind=spec.get("kind", "straight" if horizontal or abs(ba.cx - bb.cx) < 0.05 else "elbow"),
        color=spec.get("color", "accent_2"),
        weight_pt=float(spec.get("weight_pt", 1.25)),
        arrow=bool(spec.get("arrow", True)),
        dash=spec.get("dash"),
        name=f"edge-{spec.get('from')}-{spec.get('to')}",
    )
    S.connect(cxn, a, b, begin_site=sites[0], end_site=sites[1])
    if spec.get("both"):
        ln = cxn.line._get_or_add_ln()
        from pptx.oxml.ns import qn

        head = ln.find(qn("a:headEnd"))
        if head is None:
            head = ln.makeelement(qn("a:headEnd"), {})
            ln.insert(0, head)
        head.set("type", "triangle")
        head.set("w", "med")
        head.set("len", "med")
    return cxn


def _edge_label(ctx: SlideCtx, a, b, text: str) -> None:
    theme = ctx.theme
    ba, bb = _shape_box(a), _shape_box(b)
    cx, cy = (ba.cx + bb.cx) / 2, (ba.cy + bb.cy) / 2
    style = theme.style("diagram_note")
    w = max(0.6, min(1.9, wrapped_line_count(text, style.size, 1.9) * 1.0))
    # Offset perpendicular to the connection so a short arrow stays visible.
    dx, dy = bb.cx - ba.cx, bb.cy - ba.cy
    length = max((dx * dx + dy * dy) ** 0.5, 0.001)
    cx, cy = cx + dy / length * 0.20, cy - dx / length * 0.20
    lbox = Box(cx - w / 2, cy - 0.13, w, 0.26)
    shp = S.add_rect(ctx.slide, theme, lbox, fill=None, line=None, name="edge-label")
    S.fill_shape_text(shp, theme, text, style, margin_in=0.02)


# --------------------------------------------------------------------------
# 時系列・ロードマップ
# --------------------------------------------------------------------------
def draw_timeline(
    ctx: SlideCtx,
    box: Box,
    milestones: Sequence[dict],
    *,
    axis_label: str = "",
) -> Box:
    """横軸 1 本の時系列。ラベルは上下交互に置いて重なりを避ける。"""
    theme = ctx.theme
    if not milestones:
        raise DesignRuleError("draw_timeline: milestones が空です")
    axis_y = box.cy
    S.add_hline(ctx.slide, theme, box.x, axis_y, box.w, color="rule", weight_pt=1.25,
                name="timeline-axis")
    n = len(milestones)
    step = box.w / max(n - 1, 1) if n > 1 else box.w
    label_style = theme.style("diagram_label")
    note_style = theme.style("diagram_note")
    for i, m in enumerate(milestones):
        x = box.x + (i * step if n > 1 else box.w / 2)
        x = min(max(x, box.x + 0.1), box.right - 0.1)
        S.add_rect(ctx.slide, theme, Box(x - 0.045, axis_y - 0.045, 0.09, 0.09),
                   fill="accent", line=None, shape_type=MSO_SHAPE.OVAL,
                   name=f"timeline-dot-{i}")
        above = i % 2 == 0
        tw = min(2.3, box.w / max(n, 1) * 1.6)
        tx = min(max(x - tw / 2, box.x), box.right - tw)
        if above:
            tbox = Box(tx, axis_y - 0.14 - 0.72, tw, 0.72)
            anchor = "bottom"
        else:
            tbox = Box(tx, axis_y + 0.14, tw, 0.72)
            anchor = "top"
        tb = S.new_textbox(ctx.slide, tbox, anchor=anchor, name=f"timeline-label-{i}")
        S.write_paragraph(tb.text_frame, theme, str(m.get("when", "")),
                          note_style.with_(bold=True), first=True, align="center",
                          space_after_pt=1)
        S.write_paragraph(tb.text_frame, theme, str(m.get("label", "")), label_style,
                          align="center", space_after_pt=0)
    if axis_label:
        add_caption(ctx, Box(box.x, box.bottom - 0.24, box.w, 0.22), axis_label, align="right")
    return box


def draw_roadmap(
    ctx: SlideCtx,
    box: Box,
    periods: Sequence[str],
    lanes: Sequence[str],
    bars: Sequence[dict],
    *,
    lane_label_w: float = 1.9,
) -> Box:
    """ロードマップ（レーン × 期間のバー）。

    bars: [{"lane":"要素技術", "from":0, "to":2, "label":"精度評価", "tone":"accent"}]
          from/to は periods のインデックス（to は含む）
    """
    theme = ctx.theme
    if not periods or not lanes:
        raise DesignRuleError("draw_roadmap: periods と lanes は必須です")
    head_h = 0.34
    grid = Box(box.x + lane_label_w, box.y, box.w - lane_label_w, box.h)
    col_w = grid.w / len(periods)
    lane_h = (box.h - head_h) / len(lanes)
    note_style = theme.style("diagram_note")

    for i, p in enumerate(periods):
        cell = Box(grid.x + i * col_w, box.y, col_w, head_h)
        shp = S.add_rect(ctx.slide, theme, cell, fill="surface", line=None,
                         name=f"roadmap-head-{i}")
        S.fill_shape_text(shp, theme, str(p), note_style.with_(bold=True))
        if i:
            S.add_vline(ctx.slide, theme, cell.x, box.y + head_h, box.h - head_h,
                        color="rule_soft", weight_pt=0.75)
    for j, lane in enumerate(lanes):
        y = box.y + head_h + j * lane_h
        tb = S.new_textbox(ctx.slide, Box(box.x, y, lane_label_w - 0.1, lane_h),
                           anchor="middle", name=f"roadmap-lane-{j}")
        S.write_paragraph(tb.text_frame, theme, str(lane), theme.style("diagram_label"),
                          first=True, space_after_pt=0)
        S.add_hline(ctx.slide, theme, box.x, y, box.w, color="rule_soft", weight_pt=0.75)
    S.add_hline(ctx.slide, theme, box.x, box.bottom, box.w, color="rule", weight_pt=0.75)

    lane_index = {str(name): i for i, name in enumerate(lanes)}
    # Partition overlapping inclusive time intervals into separate rows per lane.
    track_ends = {str(lane): [] for lane in lanes}
    tracks = {}
    for idx, bar in sorted(enumerate(bars), key=lambda item: int(item[1].get("from", 0))):
        lane = str(bar.get("lane"))
        if lane not in track_ends:
            continue
        start, end = int(bar.get("from", 0)), int(bar.get("to", bar.get("from", 0)))
        if not 0 <= start <= end < len(periods):
            raise DesignRuleError("roadmap: from/to は期間内の昇順インデックスにしてください")
        ends = track_ends[lane]
        track = next((i for i, prior in enumerate(ends) if prior < start), len(ends))
        if track == len(ends):
            ends.append(end)
        else:
            ends[track] = end
        tracks[idx] = track
    for idx, bar in enumerate(bars):
        j = lane_index.get(str(bar.get("lane")))
        if j is None:
            ctx.deck.warnings.append(f"[{ctx.slide_id}] roadmap: 未定義レーン {bar.get('lane')!r}")
            continue
        f = max(0, int(bar.get("from", 0)))
        t = min(len(periods) - 1, int(bar.get("to", f)))
        x0 = grid.x + f * col_w + 0.06
        x1 = grid.x + (t + 1) * col_w - 0.06
        count = len(track_ends[str(bar.get("lane"))])
        track_h = lane_h / max(count, 1)
        h = min(track_h * 0.70, 0.42)
        if h < pt_to_inches(note_style.size) * 1.28 + .05:
            raise DesignRuleError("roadmap: 同一レーンの重なる予定が多すぎます。レーンかスライドを分割してください")
        y = box.y + head_h + j * lane_h + tracks[idx] * track_h + (track_h - h) / 2
        tone = bar.get("tone", "accent_pale")
        shp = S.add_rect(ctx.slide, theme, Box(x0, y, max(x1 - x0, 0.2), h),
                         fill=tone, line="accent" if tone == "accent_pale" else None,
                         line_weight_pt=0.75, name=f"roadmap-bar-{bar.get('label', '')}")
        color = "on_accent" if tone in ("accent", "accent_2") else "ink"
        S.fill_shape_text(shp, theme, str(bar.get("label", "")),
                          note_style.with_(color=color), margin_in=0.04)
    return box


# --------------------------------------------------------------------------
# 数式（編集可能なテキストとして置く）
# --------------------------------------------------------------------------
def add_formula(
    ctx: SlideCtx,
    box: Box,
    text: str,
    *,
    number: str = "",
    align: str = "center",
    size_scale: float = 1.15,
) -> Box:
    """数式を数式フォントのテキストボックスとして置く。

    OMML の数式オブジェクトではなく編集可能なテキストなので、
    PowerPoint 側で数式エディタに置き換えることもできる。
    """
    theme = ctx.theme
    style = theme.style("body").scaled(size_scale).with_(font="math", role="body")
    h = max(pt_to_inches(style.size) * 1.9, 0.34)
    formula_w = box.w - (0.72 if number else 0.0)
    if formula_w <= 0:
        raise DesignRuleError("formula: 式番号を含める領域が不足しています")
    tb = S.new_textbox(ctx.slide, Box(box.x, box.y, formula_w, h), anchor="middle", name="formula")
    S.write_paragraph(tb.text_frame, theme, text, style, first=True, align=align, space_after_pt=0)
    if number:
        nb = S.new_textbox(ctx.slide, Box(box.right - 0.6, box.y, 0.6, h), anchor="middle", name="formula-number")
        S.write_paragraph(nb.text_frame, theme, number, theme.style("note"),
                          first=True, align="right", space_after_pt=0)
    return box.with_h(h)

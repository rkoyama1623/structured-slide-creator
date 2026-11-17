"""ネイティブ表。PowerPoint 上で行列の追加・編集ができる形で作る。

罫線はヘアライン中心（縦罫を引きすぎない）、ヘッダは弱い面＋下罫線で示す。
"""

from __future__ import annotations

from typing import Any, Sequence

from pptx.util import Emu

from ..design.rules import DesignRuleError, check_font_size, check_limit
from ..units import Box, inches_to_emu, pt_to_inches
from . import shapes as S
from .components import add_caption
from .deck import SlideCtx

# 「スタイルなし・罫線なし」のテーブルスタイル GUID。
# 既定の青いテーブルスタイル（企業テンプレート風の塗り）を無効化するために使う。
PLAIN_TABLE_STYLE = "{2D5ABB26-0587-4C30-8999-92F81FD0307C}"

RATING_SYMBOLS = {
    "excellent": "◎",
    "good": "○",
    "fair": "△",
    "poor": "×",
    "na": "—",
    "◎": "◎",
    "○": "○",
    "△": "△",
    "×": "×",
    "-": "—",
}
RATING_COLORS = {"◎": "positive", "○": "ink", "△": "caution", "×": "critical", "—": "muted"}


def _set_plain_style(graphic_frame) -> None:
    tbl = graphic_frame._element.graphic.graphicData.tbl
    props = tbl.find(
        "{http://schemas.openxmlformats.org/drawingml/2006/main}tblPr"
    )
    if props is None:
        return
    props.set("firstRow", "0")
    props.set("bandRow", "0")
    for child in list(props):
        if child.tag.endswith("tableStyleId"):
            props.remove(child)
    el = props.makeelement(
        "{http://schemas.openxmlformats.org/drawingml/2006/main}tableStyleId", {}
    )
    el.text = PLAIN_TABLE_STYLE
    props.append(el)


def make_table(
    ctx: SlideCtx,
    box: Box,
    header: Sequence[str],
    rows: Sequence[Sequence[Any]],
    *,
    col_ratios: Sequence[float] | None = None,
    align: Sequence[str] | None = None,
    caption: str = "",
    numbered: bool | None = None,
    emphasize_first_col: bool = True,
    zebra: bool = False,
    row_h_in: float | None = None,
    note: str = "",
) -> Box:
    """ネイティブ表を作る。

    header: 見出し行（空リストで見出し無し）
    rows:   データ行。セルは str / 数値 / {"text":…, "color":…, "bold":…}
    align:  列ごとの寄せ ("left"|"center"|"right")。省略時は 1 列目 left、他 center
    """
    theme = ctx.theme
    rows = [list(r) for r in rows]
    if not rows and not header:
        raise DesignRuleError("make_table: 表の中身が空です（データを与えてください）")
    ncols = len(header) if header else max(len(r) for r in rows)
    nrows = len(rows) + (1 if header else 0)
    check_limit(theme, "max_table_cols", ncols, label="表の列数", hard=False)
    check_limit(theme, "max_table_rows", len(rows), label="表の行数", hard=False)

    conv = theme.conventions
    if numbered is None:
        numbered = bool(conv.get("numbered_figures", False))
    cap_text = caption
    if caption and numbered:
        cap_text = f"{conv.get('table_caption_prefix', '表')}{ctx.next_table_number()} {caption}"
    cap_above = conv.get("table_caption_position", "above") == "above"
    cap_style = theme.style("caption")
    cap_h = (pt_to_inches(cap_style.size) * 1.9) if cap_text else 0.0
    note_h = (pt_to_inches(theme.style("note").size) * 1.9) if note else 0.0

    table_box = Box(
        box.x,
        box.y + (cap_h if cap_above else 0.0),
        box.w,
        max(box.h - cap_h - note_h, 0.5),
    )
    if cap_text:
        add_caption(
            ctx,
            Box(box.x, box.y if cap_above else table_box.bottom + 0.06, box.w, cap_h),
            cap_text,
            align="left",
        )

    header_style = theme.style("table_header")
    body_style = theme.style("table_body")
    check_font_size(theme, body_style.size, role="table_body")

    from ..textmetrics import wrapped_line_count
    ratios = list(col_ratios) if col_ratios else [1.0] * ncols
    if len(ratios) != ncols:
        raise DesignRuleError("make_table: col_ratios の数が列数と一致しません")
    if any(r <= 0 for r in ratios):
        raise DesignRuleError("make_table: 列幅比率は正の数にしてください")
    if any(len(row) > ncols for row in rows):
        raise DesignRuleError("make_table: 見出しより多いセルがあります")
    widths = [table_box.w * r / sum(ratios) for r in ratios]
    all_rows = ([list(header)] if header else []) + rows
    heights = []
    for ri, values in enumerate(all_rows):
        st = header_style if header and ri == 0 else body_style
        needed = max((wrapped_line_count(_cell_parts(v, st)[0], st.size, max(.01, widths[ci] - .16))
                      * pt_to_inches(st.size) * float(theme.lay("line_spacing", 1.22)) + .07
                      for ci, v in enumerate(values)), default=.3)
        heights.append(max(row_h_in or .3, needed))
    used_h = sum(heights)
    if used_h > table_box.h + .02:
        raise DesignRuleError("make_table: セルの内容が表領域に収まりません。情報量を減らすか表を分割してください")
    gf = ctx.slide.shapes.add_table(
        nrows,
        ncols,
        inches_to_emu(table_box.x),
        inches_to_emu(table_box.y),
        inches_to_emu(table_box.w),
        inches_to_emu(used_h),
    )
    gf.name = f"table-{ctx.slide_id}"
    table = gf.table
    _set_plain_style(gf)

    # 列幅
    ratios = list(col_ratios) if col_ratios else [1.0] * ncols
    if len(ratios) != ncols:
        ratios = [1.0] * ncols
    total = sum(ratios)
    for i, r in enumerate(ratios):
        table.columns[i].width = Emu(inches_to_emu(table_box.w * r / total))

    # 行高
    for row, height in zip(table.rows, heights):
        row.height = Emu(inches_to_emu(height))

    aligns = list(align) if align else (
        ["left"] + ["center"] * (ncols - 1) if ncols > 1 else ["left"]
    )
    if len(aligns) < ncols:
        aligns += ["center"] * (ncols - len(aligns))

    def write_cell(cell, value: Any, style, al: str, *, header_cell: bool = False) -> None:
        text, color, bold = _cell_parts(value, style)
        tf = cell.text_frame
        tf.word_wrap = True
        S.clear_text(tf)
        cell.margin_left = cell.margin_right = Emu(inches_to_emu(0.08))
        cell.margin_top = cell.margin_bottom = Emu(inches_to_emu(0.035))
        from pptx.enum.text import MSO_ANCHOR

        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        st = style.with_(color=color or style.color, bold=bold if bold is not None else style.bold)
        S.write_paragraph(tf, theme, text, st, first=True, align=al, space_after_pt=0)
        if header_cell:
            S.set_cell_fill(cell, theme, "surface")
        else:
            S.set_cell_fill(cell, theme, None)

    r0 = 0
    if header:
        for c, label in enumerate(header):
            cell = table.cell(0, c)
            write_cell(cell, label, header_style, aligns[c], header_cell=True)
            S.clear_cell_border(cell, ["left", "right", "top"])
            S.set_cell_border(cell, theme, ["bottom"], color="accent", weight_pt=1.25)
        r0 = 1

    for ri, row_vals in enumerate(rows):
        for c in range(ncols):
            value = row_vals[c] if c < len(row_vals) else ""
            cell = table.cell(ri + r0, c)
            st = body_style
            if emphasize_first_col and c == 0 and ncols > 1:
                st = body_style.with_(bold=True, color="ink")
            write_cell(cell, value, st, aligns[c])
            if zebra and ri % 2 == 1:
                S.set_cell_fill(cell, theme, "surface")
            S.clear_cell_border(cell, ["left", "right"])
            S.set_cell_border(cell, theme, ["bottom"], color="rule_soft", weight_pt=0.75)
            if ri == len(rows) - 1:
                S.set_cell_border(cell, theme, ["bottom"], color="rule", weight_pt=1.0)

    if note:
        from .components import add_body_text

        add_body_text(
            ctx,
            Box(box.x, table_box.bottom + (0.06 if not cap_above else 0.06) + (cap_h if not cap_above else 0.0), box.w, note_h),
            note,
            style="note",
            strict=False,
        )
    return Box(box.x, box.y, box.w, (cap_h if cap_above else 0.0) + used_h + note_h + 0.06)


def _cell_parts(value: Any, style) -> tuple[str, str | None, bool | None]:
    if isinstance(value, dict):
        text = str(value.get("text", ""))
        return text, value.get("color"), value.get("bold")
    if isinstance(value, float):
        return (f"{value:g}", None, None)
    return (str(value) if value is not None else "", None, None)


def make_matrix(
    ctx: SlideCtx,
    box: Box,
    options: Sequence[str],
    criteria: Sequence[str],
    ratings: Sequence[Sequence[str]],
    *,
    caption: str = "",
    comments: Sequence[str] | None = None,
    col_ratios: Sequence[float] | None = None,
) -> Box:
    """評価マトリクス（◎○△×）。

    options:  行（比較対象）
    criteria: 列（評価軸）
    ratings:  options × criteria の記号（"◎"/"good" など）。空欄は "—"
    comments: 任意。行ごとの所見列を右端に追加する
    """
    header = ["", *criteria] + (["所見"] if comments else [])
    rows: list[list[Any]] = []
    for i, opt in enumerate(options):
        row: list[Any] = [opt]
        raw = list(ratings[i]) if i < len(ratings) else []
        for j in range(len(criteria)):
            sym = RATING_SYMBOLS.get(str(raw[j]).strip() if j < len(raw) else "-", "—")
            row.append({"text": sym, "color": RATING_COLORS.get(sym, "ink"), "bold": True})
        if comments:
            row.append(comments[i] if i < len(comments) else "")
        rows.append(row)
    if col_ratios is None:
        col_ratios = [1.5] + [0.8] * len(criteria) + ([2.2] if comments else [])
    return make_table(
        ctx, box, header, rows,
        col_ratios=col_ratios, caption=caption,
        align=["left"] + ["center"] * len(criteria) + (["left"] if comments else []),
    )

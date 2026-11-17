"""python-pptx の薄いラッパ。

ここから上（components / layouts）はテーマのトークンしか触らない。
図形の既定値（塗り・罫線・影なし・角丸なし・余白）はすべてこの層で決める。
"""

from __future__ import annotations

from typing import Iterable, Sequence

from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt

from ..design.rules import check_font_size
from ..design.tokens import Theme, TextStyle
from ..units import Box, inches_to_emu

ALIGN = {
    "left": PP_ALIGN.LEFT,
    "center": PP_ALIGN.CENTER,
    "right": PP_ALIGN.RIGHT,
    "justify": PP_ALIGN.JUSTIFY,
}
ANCHOR = {"top": MSO_ANCHOR.TOP, "middle": MSO_ANCHOR.MIDDLE, "bottom": MSO_ANCHOR.BOTTOM}


def rgb(theme: Theme, color: str) -> RGBColor:
    return RGBColor(*theme.rgb(color))


# --------------------------------------------------------------------------
# 図形の基本属性
# --------------------------------------------------------------------------
def kill_effects(shape) -> None:
    """影・光彩などの既定エフェクトを無効化する（AIっぽさ回避）。"""
    try:
        shape.shadow.inherit = False
    except Exception:  # noqa: BLE001 - connector などは shadow を持たない
        pass
    # LibreOffice can still apply style effects despite an empty local effectLst.
    for ref in shape._element.findall(f".//{qn('a:effectRef')}"):
        ref.set("idx", "0")


def set_fill(shape, theme: Theme, color: str | None) -> None:
    if color is None:
        shape.fill.background()
        return
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb(theme, color)


def set_line(
    shape,
    theme: Theme,
    color: str | None,
    weight_pt: float = 0.75,
    dash: str | None = None,
) -> None:
    if color is None:
        shape.line.fill.background()
        return
    shape.line.color.rgb = rgb(theme, color)
    shape.line.width = Pt(weight_pt)
    if dash:
        from pptx.enum.dml import MSO_LINE_DASH_STYLE

        mapping = {
            "dash": MSO_LINE_DASH_STYLE.DASH,
            "dot": MSO_LINE_DASH_STYLE.ROUND_DOT,
            "dashdot": MSO_LINE_DASH_STYLE.DASH_DOT,
        }
        shape.line.dash_style = mapping.get(dash, MSO_LINE_DASH_STYLE.DASH)


def add_rect(
    slide,
    theme: Theme,
    box: Box,
    *,
    fill: str | None = None,
    line: str | None = "rule",
    line_weight_pt: float = 0.75,
    dash: str | None = None,
    shape_type=MSO_SHAPE.RECTANGLE,
    name: str | None = None,
):
    x, y, w, h = box.emu
    shp = slide.shapes.add_shape(shape_type, x, y, w, h)
    set_fill(shp, theme, fill)
    set_line(shp, theme, line, line_weight_pt, dash)
    kill_effects(shp)
    shp.text_frame.word_wrap = True
    clear_text(shp.text_frame)
    if name:
        shp.name = name
    return shp


def add_hline(
    slide,
    theme: Theme,
    x: float,
    y: float,
    w: float,
    *,
    color: str = "rule",
    weight_pt: float = 1.0,
    name: str | None = None,
):
    shp = slide.shapes.add_connector(
        MSO_CONNECTOR.STRAIGHT,
        inches_to_emu(x),
        inches_to_emu(y),
        inches_to_emu(x + w),
        inches_to_emu(y),
    )
    shp.line.color.rgb = rgb(theme, color)
    shp.line.width = Pt(weight_pt)
    kill_effects(shp)
    if name:
        shp.name = name
    return shp


def add_vline(
    slide,
    theme: Theme,
    x: float,
    y: float,
    h: float,
    *,
    color: str = "rule",
    weight_pt: float = 1.0,
    name: str | None = None,
):
    shp = slide.shapes.add_connector(
        MSO_CONNECTOR.STRAIGHT,
        inches_to_emu(x),
        inches_to_emu(y),
        inches_to_emu(x),
        inches_to_emu(y + h),
    )
    shp.line.color.rgb = rgb(theme, color)
    shp.line.width = Pt(weight_pt)
    kill_effects(shp)
    if name:
        shp.name = name
    return shp


def add_connector(
    slide,
    theme: Theme,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    kind: str = "elbow",
    color: str = "accent_2",
    weight_pt: float = 1.25,
    arrow: bool = True,
    dash: str | None = None,
    name: str | None = None,
):
    """編集可能なコネクタ。kind: straight | elbow | curve"""
    ctype = {
        "straight": MSO_CONNECTOR.STRAIGHT,
        "elbow": MSO_CONNECTOR.ELBOW,
        "curve": MSO_CONNECTOR.CURVE,
    }.get(kind, MSO_CONNECTOR.ELBOW)
    cxn = slide.shapes.add_connector(
        ctype,
        inches_to_emu(start[0]),
        inches_to_emu(start[1]),
        inches_to_emu(end[0]),
        inches_to_emu(end[1]),
    )
    cxn.line.color.rgb = rgb(theme, color)
    cxn.line.width = Pt(weight_pt)
    kill_effects(cxn)
    if dash:
        set_line(cxn, theme, color, weight_pt, dash)
    if arrow:
        set_arrow_head(cxn)
    if name:
        cxn.name = name
    return cxn


def set_arrow_head(connector, kind: str = "triangle", size: str = "med") -> None:
    ln = connector.line._get_or_add_ln()
    tail = ln.find(qn("a:tailEnd"))
    if tail is None:
        tail = ln.makeelement(qn("a:tailEnd"), {})
        ln.append(tail)
    tail.set("type", kind)
    tail.set("w", size)
    tail.set("len", size)


def connect(
    connector,
    begin_shape=None,
    end_shape=None,
    begin_site: int = 3,
    end_site: int = 1,
) -> None:
    """図形に接続して、後から図形を動かしても線が追従するようにする。"""
    try:
        if begin_shape is not None:
            connector.begin_connect(begin_shape, begin_site)
        if end_shape is not None:
            connector.end_connect(end_shape, end_site)
    except Exception:  # noqa: BLE001 - 接続できない図形でも描画は継続する
        pass


# --------------------------------------------------------------------------
# テキスト
# --------------------------------------------------------------------------
def clear_text(tf) -> None:
    tf.text = ""
    for p in list(tf.paragraphs[1:]):
        p._p.getparent().remove(p._p)


def new_textbox(
    slide,
    box: Box,
    *,
    wrap: bool = True,
    anchor: str = "top",
    margins_in: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0),
    name: str | None = None,
):
    """編集可能なテキストボックス。余白は既定でゼロ（座標計算を素直にするため）。"""
    x, y, w, h = box.emu
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = wrap
    tf.vertical_anchor = ANCHOR.get(anchor, MSO_ANCHOR.TOP)
    left, top, right, bottom = margins_in
    tf.margin_left, tf.margin_top = Emu(inches_to_emu(left)), Emu(inches_to_emu(top))
    tf.margin_right, tf.margin_bottom = Emu(inches_to_emu(right)), Emu(inches_to_emu(bottom))
    clear_text(tf)
    if name:
        tb.name = name
    return tb


def apply_style(run, theme: Theme, style: TextStyle, *, allow_small: bool = False) -> None:
    """文字スタイルを run に適用する。和文/欧文のフォントを個別に指定する。"""
    pt = check_font_size(theme, style.size, role=style.role, allow_small=allow_small)
    font = run.font
    font.size = Pt(pt)
    font.bold = style.bold
    font.italic = style.italic
    font.color.rgb = rgb(theme, style.color)
    font.name = theme.font(style.font)
    # 欧文・数字は latin フォント、和文は ea フォントを明示する
    rPr = run._r.get_or_add_rPr()
    for tag, typeface in (("a:latin", theme.font("latin")), ("a:ea", theme.font(style.font))):
        el = rPr.find(qn(tag))
        if el is None:
            el = rPr.makeelement(qn(tag), {})
            rPr.append(el)
        el.set("typeface", typeface)


def write_paragraph(
    tf,
    theme: Theme,
    text: str,
    style: TextStyle,
    *,
    first: bool = False,
    align: str = "left",
    line_spacing: float | None = None,
    space_before_pt: float | None = None,
    space_after_pt: float | None = None,
    bullet_char: str | None = None,
    indent_in: float | None = None,
    allow_small: bool = False,
):
    """段落を 1 つ書き込む。bullet_char は箇条書き記号を手描きする場合に使う。"""
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.alignment = ALIGN.get(align, PP_ALIGN.LEFT)
    p.line_spacing = line_spacing if line_spacing is not None else theme.lay("line_spacing", 1.22)
    if space_after_pt is None:
        space_after_pt = theme.lay("para_space_after_pt", 5)
    p.space_after = Pt(space_after_pt)
    if space_before_pt:
        p.space_before = Pt(space_before_pt)
    if indent_in:
        pPr = p._p.get_or_add_pPr()
        pPr.set("marL", str(inches_to_emu(indent_in)))
        pPr.set("indent", str(-inches_to_emu(min(indent_in, 0.22))))
    body = f"{bullet_char} {text}" if bullet_char else text
    run = p.add_run()
    run.text = body
    apply_style(run, theme, style, allow_small=allow_small)
    no_auto_bullet(p)
    return p


def no_auto_bullet(p) -> None:
    """PowerPoint の自動箇条書きを無効化（記号はこちらで制御する）。"""
    pPr = p._p.get_or_add_pPr()
    if pPr.find(qn("a:buNone")) is None:
        pPr.append(pPr.makeelement(qn("a:buNone"), {}))


def write_rich(
    tf,
    theme: Theme,
    parts: Sequence[tuple[str, TextStyle]],
    *,
    first: bool = True,
    align: str = "left",
):
    """1 段落内に複数スタイルの run を並べる（単位付き数値の強調など）。"""
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.alignment = ALIGN.get(align, PP_ALIGN.LEFT)
    p.line_spacing = theme.lay("line_spacing", 1.22)
    for text, style in parts:
        run = p.add_run()
        run.text = text
        apply_style(run, theme, style)
    no_auto_bullet(p)
    return p


def fill_shape_text(
    shape,
    theme: Theme,
    text: str,
    style: TextStyle,
    *,
    align: str = "center",
    anchor: str = "middle",
    margin_in: float = 0.06,
    allow_small: bool = False,
):
    """図形の中にラベルを入れる（フロー図・構成図のノード）。"""
    tf = shape.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = ANCHOR.get(anchor, MSO_ANCHOR.MIDDLE)
    tf.margin_left = tf.margin_right = Emu(inches_to_emu(margin_in))
    tf.margin_top = tf.margin_bottom = Emu(inches_to_emu(margin_in * 0.6))
    clear_text(tf)
    for i, line in enumerate(str(text).split("\n")):
        write_paragraph(
            tf,
            theme,
            line,
            style,
            first=(i == 0),
            align=align,
            space_after_pt=0,
            allow_small=allow_small,
        )
    return shape


# --------------------------------------------------------------------------
# 表の罫線（python-pptx に API がないため XML を直接組む）
# --------------------------------------------------------------------------
BORDER_TAGS = {"left": "a:lnL", "right": "a:lnR", "top": "a:lnT", "bottom": "a:lnB"}
BORDER_ORDER = ["a:lnL", "a:lnR", "a:lnT", "a:lnB", "a:lnTlToBr", "a:lnBlToTr"]


def set_cell_border(
    cell,
    theme: Theme,
    edges: Iterable[str],
    *,
    color: str = "rule",
    weight_pt: float = 0.75,
    dash: str | None = None,
) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    hexcolor = theme.color(color).lstrip("#")
    for edge in edges:
        tag = BORDER_TAGS[edge]
        existing = tcPr.find(qn(tag))
        if existing is not None:
            tcPr.remove(existing)
        ln = tcPr.makeelement(
            qn(tag),
            {"w": str(int(weight_pt * 12700)), "cap": "flat", "cmpd": "sng", "algn": "ctr"},
        )
        fill = ln.makeelement(qn("a:solidFill"), {})
        clr = ln.makeelement(qn("a:srgbClr"), {"val": hexcolor})
        fill.append(clr)
        ln.append(fill)
        ln.append(ln.makeelement(qn("a:prstDash"), {"val": dash or "solid"}))
        insert_border(tcPr, ln, tag)


def clear_cell_border(cell, edges: Iterable[str]) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    for edge in edges:
        tag = BORDER_TAGS[edge]
        existing = tcPr.find(qn(tag))
        if existing is not None:
            tcPr.remove(existing)
        ln = tcPr.makeelement(qn(tag), {})
        ln.append(ln.makeelement(qn("a:noFill"), {}))
        insert_border(tcPr, ln, tag)


def insert_border(tcPr, ln, tag: str) -> None:
    """lnL/lnR/lnT/lnB は CT_TableCellProperties の所定の順序で現れる必要がある。"""
    idx = BORDER_ORDER.index(tag)
    for later in BORDER_ORDER[idx + 1 :]:
        el = tcPr.find(qn(later))
        if el is not None:
            el.addprevious(ln)
            return
    for trailing in (
        "a:cell3D",
        "a:solidFill",
        "a:noFill",
        "a:gradFill",
        "a:blipFill",
        "a:pattFill",
        "a:grpFill",
        "a:headers",
        "a:extLst",
    ):
        el = tcPr.find(qn(trailing))
        if el is not None:
            el.addprevious(ln)
            return
    tcPr.append(ln)


def set_cell_fill(cell, theme: Theme, color: str | None) -> None:
    if color is None:
        cell.fill.background()
    else:
        cell.fill.solid()
        cell.fill.fore_color.rgb = rgb(theme, color)

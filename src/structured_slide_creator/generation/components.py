"""描画コンポーネント（公開ヘルパ API）。

**この層の関数のデザインこそが承認済みデザイン。**
生成 AI は「どの関数を、どのデータで呼ぶか」だけを決める。座標・配色・
フォント・余白を関数の外から個別に指定することは想定しない。

すべての関数は実際に描いた領域（Box）を返す。レイアウトはその戻り値で縦に積む。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Sequence

from pptx.util import Emu

from ..design.rules import DesignRuleError, check_limit
from ..textmetrics import estimate_text_height_in, measure, visual_length, wrapped_line_count
from ..units import Box, inches_to_emu, pt_to_inches
from . import shapes as S
from .deck import SlideCtx

OVERFLOW_TOLERANCE = 1.12  # 概算誤差の許容（これを超えたら設計ミスとして止める）
BULLET_MARKERS = ["■", "・", "–"]


# --------------------------------------------------------------------------
# 内部ユーティリティ
# --------------------------------------------------------------------------
def _warn(ctx: SlideCtx, message: str) -> None:
    ctx.deck.warnings.append(f"[{ctx.slide_id}] {message}")


def _guard_height(
    ctx: SlideCtx,
    needed_in: float,
    box: Box,
    *,
    what: str,
    strict: bool = True,
) -> None:
    if box.h <= 0:
        raise DesignRuleError(f"{what}: 描画領域の高さが 0 以下です（レイアウトの組み立てを見直してください）")
    ratio = needed_in / box.h
    if ratio > OVERFLOW_TOLERANCE:
        msg = (
            f"{what}: 内容が領域に収まりません（必要 {needed_in:.2f}in / 枠 {box.h:.2f}in, "
            f"{ratio:.0%}）。文字を小さくするのではなく、項目を減らす・言い換えて短くする・"
            f"スライドを分割する・図解に置き換える、のいずれかで調整してください。"
        )
        if strict:
            raise DesignRuleError(msg)
        _warn(ctx, msg)
    elif ratio > 1.03:   # 丸め誤差は無視する
        _warn(ctx, f"{what}: 領域ぎりぎりです（{ratio:.0%}）。1 行削ると余裕が出ます。")


def _normalize_bullets(items: Iterable[Any]) -> list[dict]:
    """文字列／dict／ネストを (text, level) の平坦な並びに正規化する。"""
    out: list[dict] = []

    def walk(entry: Any, level: int) -> None:
        if entry is None:
            return
        if isinstance(entry, str):
            out.append({"text": entry.strip(), "level": level})
            return
        if isinstance(entry, dict):
            text = str(entry.get("text", "")).strip()
            lvl = int(entry.get("level", level))
            if text:
                out.append({"text": text, "level": lvl})
            for child in entry.get("children") or entry.get("items") or []:
                walk(child, lvl + 1)
            return
        if isinstance(entry, (list, tuple)):
            for child in entry:
                walk(child, level)
            return
        out.append({"text": str(entry), "level": level})

    for item in items:
        walk(item, 0)
    return out


# --------------------------------------------------------------------------
# タイトル周り
# --------------------------------------------------------------------------
def add_section_label(ctx: SlideCtx, text: str) -> Box:
    """タイトル上の小さなセクション表示。"""
    theme = ctx.theme
    w, _ = theme.slide_size_in
    mx = float(theme.lay("margin_x_in", 0.62))
    box = Box(mx, float(theme.lay("margin_top_in", 0.46)) - 0.02, w - 2 * mx, 0.24)
    tb = S.new_textbox(ctx.slide, box, name="section-label")
    S.write_paragraph(tb.text_frame, theme, text, theme.style("section_label"),
                      first=True, space_after_pt=0)
    return box


def add_slide_title(
    ctx: SlideCtx,
    title: str,
    lead: str | None = None,
    *,
    section: str | None = None,
    rule: bool | None = None,
) -> Box:
    """セクション／タイトル／リード文とタイトル罫線をまとめて置き、本文領域を返す。

    通常のスライドは必ずこの関数から始める。
    """
    theme = ctx.theme
    title = (title or "").strip()
    check_limit(theme, "max_title_chars", int(visual_length(title)),
                label=f"title 文字数 ({title[:20]}...)", hard=False)
    if section is not None:
        ctx.section = section
    ctx.title = title
    ctx.lead = (lead or "").strip()
    ctx.has_lead = bool(ctx.lead)

    w, _h = theme.slide_size_in
    mx = float(theme.lay("margin_x_in", 0.62))
    top = float(theme.lay("margin_top_in", 0.46))
    y = top
    if ctx.section and theme.footer.get("show_section", False) is False:
        # セクションをフッタに出さないテーマでは、タイトル上に小さく添える
        add_section_label(ctx, ctx.section)
        y += 0.26

    title_style = theme.style("slide_title")
    title_h = max(float(theme.lay("title_h_in", 0.52)),
                  wrapped_line_count(title, title_style.size, w - 2 * mx)
                  * pt_to_inches(title_style.size) * 1.22)
    tbox = Box(mx, y, w - 2 * mx, title_h)
    tb = S.new_textbox(ctx.slide, tbox, name="slide-title", anchor="top")
    S.write_paragraph(tb.text_frame, theme, title, title_style, first=True, space_after_pt=0)
    y += title_h + 0.06

    if rule is None:
        rule = bool(theme.lay("title_rule", True))
    if rule:
        S.add_hline(ctx.slide, theme, mx, y, w - 2 * mx, color="rule",
                    weight_pt=float(theme.lay("title_rule_weight_pt", 1.0)), name="title-rule")
        y += 0.10

    if ctx.has_lead:
        lead_style = theme.style("lead")
        check_limit(theme, "max_lead_chars", int(visual_length(ctx.lead)),
                    label="lead 文字数", hard=False)
        lines = wrapped_line_count(ctx.lead, lead_style.size, w - 2 * mx)
        lead_h = max(float(theme.lay("lead_h_in", 0.46)),
                     lines * pt_to_inches(lead_style.size) * 1.24)
        lbox = Box(mx, y, w - 2 * mx, lead_h)
        tb = S.new_textbox(ctx.slide, lbox, name="lead")
        S.write_paragraph(tb.text_frame, theme, ctx.lead, lead_style, first=True, space_after_pt=0)
        y += lead_h + 0.10

    bottom = float(theme.lay("content_bottom_in", 6.88))
    body = Box(mx, max(y, 0.0), w - 2 * mx, max(bottom - y, 0.5))
    ctx.set_body(body)
    return body


def add_lead_text(ctx: SlideCtx, box: Box, text: str, *, style: str = "lead") -> Box:
    """任意位置にリード文（キーメッセージ）を置く。"""
    theme = ctx.theme
    st = theme.style(style)
    needed = estimate_text_height_in([(text, st.size)], box.w,
                                     line_spacing=theme.lay("line_spacing", 1.22))
    _guard_height(ctx, needed, box, what="lead text", strict=False)
    tb = S.new_textbox(ctx.slide, box, name="lead-text")
    S.write_paragraph(tb.text_frame, theme, text, st, first=True)
    return box.with_h(min(needed, box.h))


def add_key_message(ctx: SlideCtx, box: Box, text: str) -> Box:
    """左に細いアクセント罫を引いた、落ち着いた強調ブロック（箱で囲まない）。"""
    theme = ctx.theme
    st = theme.style("heading")
    inner = Box(box.x + 0.14, box.y, box.w - 0.14, box.h)
    needed = measure(theme, [(text, st.size)], inner.w)
    h = min(max(needed, 0.3), box.h)
    S.add_vline(ctx.slide, theme, box.x, box.y + 0.02, h - 0.04,
                color="accent", weight_pt=2.5, name="keymsg-rule")
    tb = S.new_textbox(ctx.slide, Box(inner.x, inner.y, inner.w, h), name="keymsg")
    S.write_paragraph(tb.text_frame, theme, text, st, first=True, space_after_pt=0)
    return box.with_h(h)


# --------------------------------------------------------------------------
# 本文
# --------------------------------------------------------------------------
def add_body_text(
    ctx: SlideCtx,
    box: Box,
    text: str | Sequence[str],
    *,
    style: str = "body",
    align: str = "left",
    strict: bool = True,
) -> Box:
    """段落テキスト。text は文字列または段落の並び。"""
    theme = ctx.theme
    st = theme.style(style)
    paras = [text] if isinstance(text, str) else list(text)
    paras = [p for p in (str(x).strip() for x in paras) if p]
    if not paras:
        return box.with_h(0.0)
    needed = estimate_text_height_in(
        [(p, st.size) for p in paras], box.w,
        line_spacing=theme.lay("line_spacing", 1.22),
        space_after_pt=theme.lay("para_space_after_pt", 5),
    )
    _guard_height(ctx, needed, box, what=f"body text ({style})", strict=strict)
    tb = S.new_textbox(ctx.slide, box, name="body-text" if style == "body" else f"{style}-text")
    for i, p in enumerate(paras):
        S.write_paragraph(tb.text_frame, theme, p, st, first=(i == 0), align=align)
    return box.with_h(min(needed, box.h))


def add_bullet_list(
    ctx: SlideCtx,
    box: Box,
    items: Iterable[Any],
    *,
    markers: Sequence[str] | None = None,
    strict: bool = True,
    compact: bool = False,
) -> Box:
    """箇条書き。レベルごとに記号・サイズ・色・インデントをテーマが決める。"""
    theme = ctx.theme
    norm = _normalize_bullets(items)
    if not norm:
        return box.with_h(0.0)
    top_level = sum(1 for it in norm if it["level"] == 0)
    check_limit(theme, "max_bullets", top_level, label="第 1 階層の箇条書き数", hard=False)
    for it in norm:
        check_limit(theme, "max_bullet_chars", int(visual_length(it["text"])),
                    label=f"箇条書き 1 項目の長さ「{it['text'][:14]}…」", hard=False)

    markers = list(markers) if markers else BULLET_MARKERS
    indent = float(theme.lay("bullet_indent_in", 0.26))
    styles = ["bullet_1", "bullet_2", "bullet_3"]
    space_after = 0.0 if compact else theme.lay("para_space_after_pt", 5)

    lines = []
    for it in norm:
        lvl = min(it["level"], 2)
        st = theme.style(styles[lvl])
        lines.append((it["text"], st.size))
    needed = estimate_text_height_in(
        lines, box.w, line_spacing=theme.lay("line_spacing", 1.22),
        space_after_pt=space_after, indent_in=indent,
    )
    _guard_height(ctx, needed, box, what="bullet list", strict=strict)

    tb = S.new_textbox(ctx.slide, box, name="bullets")
    for i, it in enumerate(norm):
        lvl = min(it["level"], 2)
        S.write_paragraph(
            tb.text_frame, theme, it["text"], theme.style(styles[lvl]),
            first=(i == 0), bullet_char=markers[min(lvl, len(markers) - 1)],
            indent_in=indent * (lvl + 1), space_after_pt=space_after,
        )
    return box.with_h(min(needed, box.h))


def add_section_heading(ctx: SlideCtx, box: Box, text: str, *, rule: bool = True) -> Box:
    """スライド内の小見出し。下にヘアラインを引く。"""
    theme = ctx.theme
    st = theme.style("heading")
    h = pt_to_inches(st.size) * 1.4
    tb = S.new_textbox(ctx.slide, Box(box.x, box.y, box.w, h), name="heading")
    S.write_paragraph(tb.text_frame, theme, text, st, first=True, space_after_pt=0)
    used = h
    if rule:
        S.add_hline(ctx.slide, theme, box.x, box.y + h + 0.03, box.w,
                    color="rule_soft", weight_pt=0.75, name="heading-rule")
        used += 0.09
    return box.with_h(used)


def add_caption(ctx: SlideCtx, box: Box, text: str, *, align: str = "left") -> Box:
    theme = ctx.theme
    st = theme.style("caption")
    h = measure(theme, [(text, st.size)], box.w, space_after_pt=0)
    tb = S.new_textbox(ctx.slide, Box(box.x, box.y, box.w, max(h, 0.2)), name="caption")
    S.write_paragraph(tb.text_frame, theme, text, st, first=True, align=align, space_after_pt=0)
    return box.with_h(max(h, 0.2))


def add_reference_note(
    ctx: SlideCtx,
    items: Sequence[str],
    *,
    box: Box | None = None,
    prefix: str | None = None,
) -> Box:
    """出典・脚注。本文領域の最下部に小さく置く。内容は呼び出し側が与えたものだけを書く。"""
    theme = ctx.theme
    items = [str(x).strip() for x in items if str(x).strip()]
    if not items:
        return Box(0, 0, 0, 0)
    st = theme.style("note")
    bracket = (theme.conventions.get("reference_style") == "bracket")
    lines = []
    for i, text in enumerate(items, start=1):
        if prefix is not None:
            lines.append(f"{prefix}{text}")
        elif bracket:
            lines.append(text if text.startswith("[") else f"[{i}] {text}")
        else:
            lines.append(f"※ {text}")
    if box is None:
        w, _h = theme.slide_size_in
        mx = float(theme.lay("margin_x_in", 0.62))
        bottom = float(theme.lay("content_bottom_in", 6.88))
        h = measure(theme, [(x, st.size) for x in lines], w - 2 * mx, space_after_pt=1)
        box = Box(mx, bottom - h, w - 2 * mx, h)
    tb = S.new_textbox(ctx.slide, box, name="reference-note")
    for i, line in enumerate(lines):
        S.write_paragraph(tb.text_frame, theme, line, st, first=(i == 0), space_after_pt=1)
    return box


def add_note_block(ctx: SlideCtx, box: Box, text: str | Sequence[str], *, tone: str = "surface") -> Box:
    """補助情報の弱い面（前提・注意など）。囲みは最小限、塗りのみで罫線なし。"""
    theme = ctx.theme
    paras = [text] if isinstance(text, str) else list(text)
    st = theme.style("note")
    needed = measure(theme, [(p, st.size) for p in paras], box.w - 0.24, space_after_pt=2)
    h = min(max(needed + 0.18, 0.34), box.h)
    S.add_rect(ctx.slide, theme, Box(box.x, box.y, box.w, h), fill=tone, line=None,
               name="note-block")
    tb = S.new_textbox(ctx.slide, Box(box.x + 0.12, box.y + 0.09, box.w - 0.24, h - 0.18),
                       name="note-text")
    for i, p in enumerate(paras):
        S.write_paragraph(tb.text_frame, theme, str(p), st, first=(i == 0), space_after_pt=2)
    return box.with_h(h)


# --------------------------------------------------------------------------
# 図・画像
# --------------------------------------------------------------------------
def add_image_with_caption(
    ctx: SlideCtx,
    box: Box,
    image_path: str | Path,
    *,
    caption: str = "",
    numbered: bool | None = None,
    frame: bool = True,
    align: str = "center",
) -> Box:
    """画像を領域内にアスペクト比を保って収め、必要ならキャプションを付ける。

    画像が見つからない場合は、同じ寸法のプレースホルダ枠を描いて警告を残す
    （存在しない図を勝手に捏造しないため）。
    """
    theme = ctx.theme
    path = Path(image_path)
    cap_style = theme.style("caption")
    conv = theme.conventions
    if numbered is None:
        numbered = bool(conv.get("numbered_figures", False))
    cap_text = caption
    if caption and numbered:
        cap_text = f"{conv.get('figure_caption_prefix', '図')}{ctx.next_figure_number()} {caption}"
    cap_h = (measure(theme, [(cap_text, cap_style.size)], box.w, space_after_pt=0) + 0.06
             if cap_text else 0.0)
    img_box = Box(box.x, box.y, box.w, max(box.h - cap_h, 0.4))

    if not path.exists():
        _warn(ctx, f"画像が見つかりません: {path}（プレースホルダを配置しました）")
        S.add_rect(ctx.slide, theme, img_box, fill="surface", line="rule", dash="dash",
                   name="image-placeholder")
        tb = S.new_textbox(ctx.slide, img_box.inset(0.1), anchor="middle")
        S.write_paragraph(tb.text_frame, theme, f"[画像未配置] {path.name}",
                          theme.style("note"), first=True, align="center", space_after_pt=0)
    else:
        from PIL import Image

        with Image.open(path) as im:
            iw, ih = im.size
        scale = min(img_box.w / (iw / 96.0), img_box.h / (ih / 96.0))
        dw, dh = (iw / 96.0) * scale, (ih / 96.0) * scale
        dx = img_box.x + (img_box.w - dw) / 2 if align == "center" else img_box.x
        dy = img_box.y + (img_box.h - dh) / 2
        pic = ctx.slide.shapes.add_picture(
            str(path), inches_to_emu(dx), inches_to_emu(dy),
            Emu(inches_to_emu(dw)), Emu(inches_to_emu(dh)),
        )
        pic.name = f"figure-{path.stem}"
        if frame:
            S.set_line(pic, theme, "rule_soft", 0.75)
    if cap_text:
        add_caption(ctx, Box(box.x, img_box.bottom + 0.06, box.w, cap_h), cap_text,
                    align="center" if align == "center" else "left")
    return box


def add_figure_placeholder(ctx: SlideCtx, box: Box, label: str = "図を配置") -> Box:
    """図の予定地。まだ素材が無い段階の構成確認に使う。"""
    theme = ctx.theme
    S.add_rect(ctx.slide, theme, box, fill="surface", line="rule", dash="dash",
               name="figure-placeholder")
    tb = S.new_textbox(ctx.slide, box.inset(0.12), anchor="middle")
    S.write_paragraph(tb.text_frame, theme, label, theme.style("note"),
                      first=True, align="center", space_after_pt=0)
    return box


def add_badge(ctx: SlideCtx, box: Box, text: str, *, fill: str = "accent_pale",
              color: str = "accent") -> Box:
    """短いラベル（条件名・区分）。角丸・影は使わない。"""
    theme = ctx.theme
    shp = S.add_rect(ctx.slide, theme, box, fill=fill, line=None, name="badge")
    S.fill_shape_text(shp, theme, text, theme.style("caption").with_(color=color, bold=True))
    return box

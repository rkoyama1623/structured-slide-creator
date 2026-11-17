"""文字幅の概算。

PowerPoint の実レンダリングと完全一致はしないが、
「はみ出しそう／詰め込みすぎ」を生成時と検査時の両方で同じ基準で判定するために使う。
和文は全角 1.0em、ASCII は約 0.52em として見積もる。
"""

from __future__ import annotations

import math
import unicodedata

from .units import pt_to_inches


def char_width_em(ch: str) -> float:
    if ch == "\t":
        return 2.0
    cat = unicodedata.east_asian_width(ch)
    if cat in ("W", "F"):
        return 1.0
    if cat == "A":  # ambiguous（ギリシャ文字・記号など）は和文扱いが安全
        return 0.92
    if ch in "ilj|!.,'’:;()[]":
        return 0.30
    if ch in "mwMW@":
        return 0.82
    if ch.isdigit() or ch.isalpha():
        return 0.55
    return 0.45


def text_width_em(text: str) -> float:
    return sum(char_width_em(c) for c in text)


def visual_length(text: str) -> float:
    """和文 1.0 / 欧文 0.5 換算の「文字数」。情報量の上限判定に使う。"""
    return text_width_em(text)


def wrapped_line_count(text: str, font_pt: float, width_in: float) -> int:
    """折り返し後の行数を概算する。"""
    if not text:
        return 1
    if width_in <= 0:
        return 1
    em_in = pt_to_inches(font_pt)
    capacity_em = width_in / em_in
    lines = 0
    for raw_line in text.split("\n"):
        if not raw_line:
            lines += 1
            continue
        lines += max(1, math.ceil(text_width_em(raw_line) / max(capacity_em, 0.5)))
    return lines


def estimate_text_height_in(
    lines: list[tuple[str, float]],
    width_in: float,
    *,
    line_spacing: float = 1.22,
    space_after_pt: float = 5.0,
    indent_in: float = 0.0,
) -> float:
    """(本文, フォントpt) の並びから必要高さ(inch)を概算する。"""
    total = 0.0
    for text, pt in lines:
        n = wrapped_line_count(text, pt, max(width_in - indent_in, 0.4))
        total += n * pt_to_inches(pt) * line_spacing + pt_to_inches(space_after_pt)
    return total


def fits(height_in: float, box_h_in: float, tolerance: float = 0.02) -> bool:
    return height_in <= box_h_in + tolerance


def autoshrink_pt(
    lines: list[tuple[str, float]],
    width_in: float,
    box_h_in: float,
    *,
    min_pt: float,
    line_spacing: float = 1.22,
    space_after_pt: float = 5.0,
    step: float = 0.5,
) -> float | None:
    """枠に収まる縮小率を探す。min_pt を下回る場合は None（＝内容を削るべき）。"""
    factor = 1.0
    while factor > 0.3:
        scaled = [(t, round(pt * factor, 1)) for t, pt in lines]
        if min(pt for _, pt in scaled) < min_pt:
            return None
        h = estimate_text_height_in(
            scaled, width_in, line_spacing=line_spacing, space_after_pt=space_after_pt
        )
        if fits(h, box_h_in):
            return factor
        factor -= step / max(1.0, max(pt for _, pt in lines))
    return None


def measure(theme, lines: list[tuple[str, float]], width_in: float, *,
            space_after_pt: float | None = None, indent_in: float = 0.0) -> float:
    """テーマの行間・段落間隔で高さを見積もる（描画と検査で同じ値を使うための入口）。"""
    return estimate_text_height_in(
        lines,
        width_in,
        line_spacing=float(theme.lay("line_spacing", 1.22)),
        space_after_pt=(float(theme.lay("para_space_after_pt", 5))
                        if space_after_pt is None else float(space_after_pt)),
        indent_in=indent_in,
    )

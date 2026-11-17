"""WCAG 相対輝度によるコントラスト計算。低コントラスト検査で使う。"""

from __future__ import annotations


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    v = value.lstrip("#")
    if len(v) == 3:
        v = "".join(ch * 2 for ch in v)
    if len(v) != 6:
        raise ValueError(f"color must be #RRGGBB: {value!r}")
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#%02X%02X%02X" % rgb


def relative_luminance(rgb: tuple[int, int, int]) -> float:
    def ch(c: int) -> float:
        s = c / 255.0
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: str | tuple[int, int, int], bg: str | tuple[int, int, int]) -> float:
    f = hex_to_rgb(fg) if isinstance(fg, str) else fg
    b = hex_to_rgb(bg) if isinstance(bg, str) else bg
    lf, lb = relative_luminance(f), relative_luminance(b)
    hi, lo = max(lf, lb), min(lf, lb)
    return (hi + 0.05) / (lo + 0.05)


def required_ratio(font_pt: float, bold: bool = False) -> float:
    """WCAG 2.1 の大文字判定（18pt 以上、または 14pt 以上の太字）。"""
    large = font_pt >= 18 or (bold and font_pt >= 14)
    return 3.0 if large else 4.5

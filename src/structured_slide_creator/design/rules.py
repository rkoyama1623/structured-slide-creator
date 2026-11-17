"""デザイン規則の強制。

プロンプトで守らせるのではなく、関数が例外を投げて実行を止める。
（記事の「12pt 未満は ValueError」と同じ思想を、テーマ駆動に一般化したもの）
"""

from __future__ import annotations


class DesignRuleError(ValueError):
    """テーマが定めたデザイン規則に違反した時に送出する。"""


def check_font_size(theme, pt: float, *, role: str = "text", allow_small: bool = False) -> float:
    """フォントサイズの下限を強制する。

    role が body / bullet / lead で始まる場合は min_body_pt、
    それ以外（caption, note, footer, 図中ラベル）は min_font_pt を下限とする。
    allow_small=True は図中の添字など、明示的に例外を認める場合のみ。
    """
    pt = float(pt)
    if allow_small:
        floor = 8.0
    elif role.startswith(("body", "bullet", "lead", "heading")):
        # 本文系（散文）は読ませる文字なので最も高い下限
        floor = float(theme.limits["min_body_pt"])
    elif role.startswith("footer"):
        # フッタ・ページ番号は読み物ではないので別枠（ただし下限はある）
        floor = float(theme.limits.get("min_chrome_pt", 8.5))
    elif role.startswith("table"):
        # 表のセルは行数を確保するため本文より小さくてよいが、独自の下限を持つ
        floor = float(theme.limits.get("min_table_pt", theme.limits["min_font_pt"]))
    else:
        # caption / note / footer / 図中ラベルなど
        floor = float(theme.limits["min_font_pt"])
    if pt < floor:
        raise DesignRuleError(
            f"font size {pt}pt is below the theme floor for role={role!r} "
            f"({floor}pt, theme={theme.name}). "
            f"文字を小さくするのではなく、情報量を減らすかスライドを分割してください。"
        )
    return pt


def check_limit(theme, key: str, actual: int, *, label: str = "", hard: bool = True) -> list[str]:
    """limits.* の上限チェック。hard=True なら例外、False なら警告文字列を返す。"""
    cap = theme.limits.get(key)
    if cap is None:
        return []
    if actual > cap:
        msg = (
            f"{label or key}: {actual} が上限 {cap} を超えています（theme={theme.name}）。"
            f" 分割・要約・図解への置き換えを検討してください。"
        )
        if hard:
            raise DesignRuleError(msg)
        return [msg]
    return []


def check_inside_slide(theme, box, *, name: str = "shape", tol: float = 0.01) -> None:
    """スライド外へのはみ出しを禁止する。"""
    w, h = theme.slide_size_in
    if box.x < -tol or box.y < -tol or box.right > w + tol or box.bottom > h + tol:
        raise DesignRuleError(
            f"{name} {box} はスライド範囲 ({w}x{h} in) をはみ出しています。"
        )

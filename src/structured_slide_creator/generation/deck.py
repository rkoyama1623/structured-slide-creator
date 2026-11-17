"""デッキ（プレゼンテーション全体）とスライド 1 枚のコンテキスト。

企業テンプレートは一切読み込まない。python-pptx の既定ファイル（Office 既定の
空テンプレート）の「白紙」レイアウトだけを使い、見た目はすべてテーマから描く。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.oxml.ns import qn
from pptx.util import Emu

from ..design.tokens import Theme, load_theme
from ..units import Box, inches_to_emu
from . import shapes as S

BLANK_LAYOUT_INDEX = 6  # python-pptx 既定テンプレートの「白紙」レイアウト


@dataclass
class DeckMeta:
    title: str = ""
    subtitle: str = ""
    author: str = ""
    affiliation: str = ""
    date: str = ""
    event: str = ""
    footer_text: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


class SlideCtx:
    """スライド 1 枚の描画コンテキスト。

    components / layouts は常にこのオブジェクト経由で描く。
    `body` は「タイトルとリード文の下」の使用可能領域。
    """

    def __init__(self, deck: "Deck", slide, index: int, *, section: str = "", slide_id: str = ""):
        self.deck = deck
        self.slide = slide
        self.theme: Theme = deck.theme
        self.index = index            # 0 基点
        self.slide_id = slide_id or f"slide{index + 1:02d}"
        self.section = section
        self.title = ""
        self.lead = ""
        self.has_lead = False
        self._body: Box | None = None
        self.show_footer = True
        self.notes: list[str] = []

    # --- 領域 ----------------------------------------------------------
    @property
    def body(self) -> Box:
        if self._body is None:
            self._body = self.theme.content_box(has_lead=self.has_lead)
        return self._body

    def set_body(self, box: Box) -> None:
        self._body = box

    @property
    def full(self) -> Box:
        return self.theme.full_box()

    # --- 便利メソッド --------------------------------------------------
    def add_speaker_note(self, text: str) -> None:
        if not text:
            return
        self.notes.append(text)
        tf = self.slide.notes_slide.notes_text_frame
        tf.text = "\n".join(self.notes)

    def next_figure_number(self) -> int:
        self.deck.figure_count += 1
        return self.deck.figure_count

    def next_table_number(self) -> int:
        self.deck.table_count += 1
        return self.deck.table_count


class Deck:
    """PPTX のビルダ。テーマとメタ情報を持ち、スライドを順に積む。"""

    def __init__(self, theme: Theme | str = "neutral", meta: DeckMeta | None = None):
        self.theme = theme if isinstance(theme, Theme) else load_theme(theme)
        self.meta = meta or DeckMeta()
        self.prs = Presentation()
        w, h = self.theme.slide_size_in
        self.prs.slide_width = Emu(inches_to_emu(w))
        self.prs.slide_height = Emu(inches_to_emu(h))
        self.contexts: list[SlideCtx] = []
        self.figure_count = 0
        self.table_count = 0
        self.warnings: list[str] = []   # 生成時に気づいた軽微な問題（レビュー報告に載せる）
        self._apply_theme_fonts()

    # --- スライド追加 --------------------------------------------------
    def add_slide(self, *, section: str = "", slide_id: str = "") -> SlideCtx:
        layout = self.prs.slide_layouts[BLANK_LAYOUT_INDEX]
        slide = self.prs.slides.add_slide(layout)
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = S.rgb(self.theme, "bg")
        # 白紙レイアウトでもプレースホルダが残る場合があるため念のため除去する
        for ph in list(slide.placeholders):
            ph._element.getparent().remove(ph._element)
        ctx = SlideCtx(self, slide, len(self.contexts), section=section, slide_id=slide_id)
        self.contexts.append(ctx)
        return ctx

    # --- 仕上げ --------------------------------------------------------
    def finalize(self) -> None:
        """フッタ（ページ番号・セクション・固定文言）を全スライドに入れる。"""
        cfg = self.theme.footer
        total = len(self.contexts)
        w, _h = self.theme.slide_size_in
        mx = float(self.theme.lay("margin_x_in", 0.62))
        style = self.theme.style("footer")
        base_y = float(self.theme.lay("content_bottom_in", 6.88)) + 0.06
        for ctx in self.contexts:
            if not ctx.show_footer:
                continue
            left_bits: list[str] = []
            if cfg.get("show_section") and ctx.section:
                left_bits.append(ctx.section)
            if cfg.get("show_deck_title") and self.meta.title:
                left_bits.append(self.meta.title)
            fixed = self.meta.footer_text or cfg.get("text") or ""
            if fixed:
                left_bits.append(fixed)
            if left_bits:
                tb = S.new_textbox(
                    ctx.slide, Box(mx, base_y, w - 2 * mx - 1.0, 0.26), name="footer-left"
                )
                S.write_paragraph(
                    tb.text_frame, self.theme, " / ".join(left_bits), style,
                    first=True, space_after_pt=0,
                )
            if cfg.get("show_page_number"):
                fmt = cfg.get("page_number_format", "{page}")
                text = fmt.format(page=ctx.index + 1, total=total)
                tb = S.new_textbox(
                    ctx.slide, Box(w - mx - 1.0, base_y, 1.0, 0.26), name="footer-page"
                )
                S.write_paragraph(
                    tb.text_frame, self.theme, text, style,
                    first=True, align="right", space_after_pt=0,
                )

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.prs.save(str(path))
        return path

    # --- 内部 ----------------------------------------------------------
    def _apply_theme_fonts(self) -> None:
        """スライドマスタのテーマフォントを差し替える。

        本文はすべて run レベルで明示指定するが、表・グラフなどの
        継承テキストが Calibri のまま残らないようにしておく。
        """
        latin = self.theme.font("latin")
        ja = self.theme.font("ja")
        try:
            for master in self.prs.slide_masters:
                theme_part = master.part.part_related_by(RT.THEME)
                root = theme_part._element if hasattr(theme_part, "_element") else None
                if root is None:
                    from lxml import etree

                    root = etree.fromstring(theme_part.blob)
                for scheme in ("a:majorFont", "a:minorFont"):
                    node = root.find(f".//{qn(scheme)}")
                    if node is None:
                        continue
                    lt = node.find(qn("a:latin"))
                    if lt is not None:
                        lt.set("typeface", latin)
                    ea = node.find(qn("a:ea"))
                    if ea is not None:
                        ea.set("typeface", ja)
                # Generic OPC parts serialize their blob, not this parsed tree.
                from lxml import etree
                theme_part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
        except Exception:  # noqa: BLE001 - 失敗してもテキストは run 単位で正しい
            pass

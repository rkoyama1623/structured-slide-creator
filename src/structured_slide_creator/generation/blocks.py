"""コンテンツブロックのディスパッチャ。

レイアウトは「領域（Box）を決める」ことに専念し、
その領域に何を描くかは共通のブロック仕様で指定する。
この分離によって、少ないレイアウト数でも組み合わせの表現力が出る。

ブロック仕様の例::

    {"type": "bullets", "items": ["…", {"text": "…", "children": ["…"]}]}
    {"type": "chart", "kind": "bar", "categories": [...], "series": [...]}
    {"type": "diagram", "nodes": [...], "edges": [...]}
"""

from __future__ import annotations

from typing import Any

from ..design.rules import DesignRuleError
from ..units import Box
from . import components as C
from . import diagram as D
from .charts import add_chart
from .deck import SlideCtx
from .tables import make_matrix, make_table

BLOCK_TYPES = [
    "text", "bullets", "key_message", "note", "caption", "formula",
    "image", "figure", "chart", "table", "matrix",
    "flow", "steps", "diagram", "timeline", "roadmap", "compare", "split",
    "empty",
]


def render_block(ctx: SlideCtx, box: Box, block: Any, *, strict: bool = True) -> Box:
    """ブロック仕様を領域に描画し、実際に使った領域を返す。"""
    if block is None:
        return box.with_h(0.0)
    if isinstance(block, str):
        block = {"type": "text", "text": block}
    if isinstance(block, list):
        return render_stack(ctx, box, block, strict=strict)
    if not isinstance(block, dict):
        raise DesignRuleError(f"render_block: 不正なブロック指定 {block!r}")

    btype = str(block.get("type", "")).lower()
    if not btype:
        # type 省略時はキーから推定する（書きやすさのため）
        for key in ("items", "text", "image", "chart", "table", "nodes", "steps", "flow"):
            if key in block:
                btype = {"items": "bullets", "text": "text", "image": "image",
                         "chart": "chart", "table": "table", "nodes": "diagram",
                         "steps": "steps", "flow": "flow"}[key]
                break
    if btype not in BLOCK_TYPES:
        raise DesignRuleError(
            f"unknown block type {btype!r}. available: {BLOCK_TYPES}"
        )

    heading = block.get("heading")
    used_top = 0.0
    if heading:
        used = C.add_section_heading(ctx, box, str(heading))
        used_top = used.h + 0.06
        box = Box(box.x, box.y + used_top, box.w, box.h - used_top)

    out = _dispatch(ctx, box, btype, block, strict=strict)
    return Box(out.x, out.y - used_top, out.w, out.h + used_top)


def render_stack(ctx: SlideCtx, box: Box, blocks: list, *, gap: float | None = None,
                 strict: bool = True) -> Box:
    """複数ブロックを縦に積む。高さ比は ratio（既定は内容に応じた自動配分）。"""
    theme = ctx.theme
    gap = float(theme.lay("block_gap_in", 0.22)) if gap is None else gap
    blocks = [b for b in blocks if b is not None]
    if not blocks:
        return box.with_h(0.0)
    ratios = [float(b.get("ratio", 1.0)) if isinstance(b, dict) else 1.0 for b in blocks]
    fixed = [float(b.get("height_in", 0.0)) if isinstance(b, dict) else 0.0 for b in blocks]
    free_h = box.h - gap * (len(blocks) - 1) - sum(fixed)
    total_ratio = sum(r for r, f in zip(ratios, fixed) if not f) or 1.0
    y = box.y
    for b, r, f in zip(blocks, ratios, fixed):
        h = f if f else free_h * (r / total_ratio)
        render_block(ctx, Box(box.x, y, box.w, max(h, 0.2)), b, strict=strict)
        y += h + gap
    return box


def _dispatch(ctx: SlideCtx, box: Box, btype: str, b: dict, *, strict: bool) -> Box:
    if btype == "empty":
        return box.with_h(0.0)
    if btype == "text":
        return C.add_body_text(ctx, box, b.get("text") or b.get("paragraphs") or "",
                               style=b.get("style", "body"), align=b.get("align", "left"),
                               strict=strict)
    if btype == "bullets":
        return C.add_bullet_list(ctx, box, b.get("items") or [],
                                 markers=b.get("markers"), compact=bool(b.get("compact")),
                                 strict=strict)
    if btype == "key_message":
        return C.add_key_message(ctx, box, str(b.get("text", "")))
    if btype == "note":
        return C.add_note_block(ctx, box, b.get("text") or b.get("items") or "",
                                tone=b.get("tone", "surface"))
    if btype == "caption":
        return C.add_caption(ctx, box, str(b.get("text", "")), align=b.get("align", "left"))
    if btype == "formula":
        return D.add_formula(ctx, box, str(b.get("text", "")), number=str(b.get("number", "")),
                             align=b.get("align", "center"))
    if btype == "image":
        return C.add_image_with_caption(ctx, box, b.get("image") or b.get("path") or "",
                                        caption=b.get("caption", ""),
                                        numbered=b.get("numbered"),
                                        frame=bool(b.get("frame", True)))
    if btype == "figure":
        return C.add_figure_placeholder(ctx, box, str(b.get("label", "図を配置")))
    if btype == "chart":
        return add_chart(ctx, box, str(b.get("kind", "bar")), b.get("categories") or [],
                         b.get("series") or [], caption=b.get("caption", ""),
                         y_title=b.get("y_title", ""), x_title=b.get("x_title", ""),
                         number_format=b.get("number_format"), legend=b.get("legend"),
                         gridlines=bool(b.get("gridlines", True)),
                         y_min=b.get("y_min"), y_max=b.get("y_max"))
    if btype == "table":
        return make_table(ctx, box, b.get("header") or [], b.get("rows") or [],
                          col_ratios=b.get("col_ratios"), align=b.get("align"),
                          caption=b.get("caption", ""), zebra=bool(b.get("zebra")),
                          note=b.get("note", ""),
                          emphasize_first_col=bool(b.get("emphasize_first_col", True)))
    if btype == "matrix":
        return make_matrix(ctx, box, b.get("options") or [], b.get("criteria") or [],
                           b.get("ratings") or [], caption=b.get("caption", ""),
                           comments=b.get("comments"))
    if btype == "flow":
        D.draw_process_flow(ctx, box, b.get("steps") or b.get("items") or [],
                            direction=b.get("direction", "h"),
                            numbered=bool(b.get("numbered", True)),
                            kind=b.get("kind", "box"))
        return box
    if btype == "steps":
        return D.draw_step_list(ctx, box, b.get("steps") or b.get("items") or [])
    if btype == "diagram":
        D.draw_system_diagram(ctx, box, b.get("nodes") or [], b.get("edges") or [],
                              rows=b.get("rows"), cols=b.get("cols"),
                              groups=b.get("groups") or ())
        return box
    if btype == "timeline":
        return D.draw_timeline(ctx, box, b.get("milestones") or b.get("items") or [],
                               axis_label=b.get("axis_label", ""))
    if btype == "roadmap":
        return D.draw_roadmap(ctx, box, b.get("periods") or [], b.get("lanes") or [],
                              b.get("bars") or [])
    if btype == "compare":
        D.draw_comparison_layout(ctx, box, b.get("columns") or [], ratios=b.get("ratios"))
        return box
    if btype == "split":
        regions = D.draw_split_layout(ctx, box, ratios=b.get("ratios", (1, 1)),
                                      headings=b.get("headings"),
                                      divider=bool(b.get("divider", False)))
        for region, child in zip(regions, b.get("blocks") or []):
            render_block(ctx, region, child, strict=strict)
        return box
    raise DesignRuleError(f"block type {btype!r} is not implemented")

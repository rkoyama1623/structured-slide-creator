"""描画 API の公開窓口。

Skill からはこのモジュール名だけを覚えれば足りる:

    from structured_slide_creator.generation import (
        Deck, DeckMeta, build_deck, build_slide,
        add_slide_title, add_lead_text, add_body_text, add_bullet_list,
        add_section_heading, add_image_with_caption, add_reference_note,
        make_table, make_matrix, add_chart,
        draw_split_layout, draw_comparison_layout, draw_process_flow,
        draw_system_diagram, draw_step_list, draw_timeline, draw_roadmap,
        add_formula, render_block,
    )
"""

from .blocks import render_block, render_stack
from .build import BuildResult, build_deck
from .charts import add_chart
from .components import (
    add_badge,
    add_body_text,
    add_bullet_list,
    add_caption,
    add_figure_placeholder,
    add_image_with_caption,
    add_key_message,
    add_lead_text,
    add_note_block,
    add_reference_note,
    add_section_heading,
    add_section_label,
    add_slide_title,
)
from .deck import Deck, DeckMeta, SlideCtx
from .diagram import (
    add_formula,
    draw_comparison_layout,
    draw_process_flow,
    draw_roadmap,
    draw_split_layout,
    draw_step_list,
    draw_system_diagram,
    draw_timeline,
)
from .layouts import LAYOUTS, build_slide, catalog_entries
from .tables import make_matrix, make_table

__all__ = [
    "Deck", "DeckMeta", "SlideCtx", "BuildResult", "build_deck", "build_slide",
    "LAYOUTS", "catalog_entries", "render_block", "render_stack",
    "add_slide_title", "add_section_label", "add_lead_text", "add_key_message",
    "add_body_text", "add_bullet_list", "add_section_heading", "add_caption",
    "add_note_block", "add_reference_note", "add_image_with_caption",
    "add_figure_placeholder", "add_badge",
    "make_table", "make_matrix", "add_chart",
    "draw_split_layout", "draw_comparison_layout", "draw_process_flow",
    "draw_system_diagram", "draw_step_list", "draw_timeline", "draw_roadmap",
    "add_formula",
]

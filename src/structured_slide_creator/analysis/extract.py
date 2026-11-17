"""Local-only structural extraction. Call sanitize before sharing the result."""

from pathlib import Path
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from ..review.checks import shape_box, solid_color, walk_shapes
from ..units import EMU_PER_INCH


def extract_pptx(path):
    prs = Presentation(str(path))
    slides = []
    for index, slide in enumerate(prs.slides, 1):
        shapes = []
        for shape in walk_shapes(slide.shapes):
            kind = (
                "group"
                if shape.shape_type == MSO_SHAPE_TYPE.GROUP
                else "image"
                if shape.shape_type == MSO_SHAPE_TYPE.PICTURE
                else "table"
                if shape.has_table
                else "chart"
                if shape.has_chart
                else "connector"
                if shape.shape_type == MSO_SHAPE_TYPE.LINE
                else "text"
                if shape.has_text_frame and shape.text.strip()
                else "shape"
            )
            texts, runs, levels = [], [], []
            frames = [shape.text_frame] if shape.has_text_frame else []
            if shape.has_table:
                frames.extend(
                    c.text_frame
                    for row in shape.table.rows
                    for c in row.cells
                    if not c.is_spanned
                )
            for tf in frames:
                texts.append(tf.text)
                for p in tf.paragraphs:
                    levels.append(p.level)
                    for r in p.runs:
                        try:
                            color = (
                                "#" + str(r.font.color.rgb)
                                if r.font.color.rgb
                                else None
                            )
                        except (AttributeError, TypeError):
                            color = None
                        runs.append(
                            {
                                "font": r.font.name,
                                "size": r.font.size.pt if r.font.size else None,
                                "bold": r.font.bold,
                                "color": color,
                            }
                        )
            shapes.append(
                {
                    "id": shape.shape_id,
                    "name": shape.name,
                    "kind": kind,
                    "box": vars(shape_box(shape)),
                    "text": "\n".join(texts),
                    "runs": runs,
                    "levels": levels,
                    "fill": solid_color(shape.fill) if hasattr(shape, "fill") else None,
                }
            )
        inherited = []
        for source, container in [
            ("layout", slide.slide_layout),
            ("master", slide.slide_layout.slide_master),
        ]:
            for s in walk_shapes(container.shapes):
                if s.shape_type == MSO_SHAPE_TYPE.PICTURE:
                    inherited.append(
                        {
                            "source": source,
                            "kind": "image",
                            "inherit": False,
                            "needs_human_review": True,
                        }
                    )
        slides.append(
            {
                "index": index,
                "layout_name": slide.slide_layout.name,
                "master_name": slide.slide_layout.slide_master.name,
                "shapes": shapes,
                "inherited_images": inherited,
            }
        )
    return {
        "source": str(Path(path).resolve()),
        "width": prs.slide_width / EMU_PER_INCH,
        "height": prs.slide_height / EMU_PER_INCH,
        "slides": slides,
    }

"""Conservative rule-based layout classification with evidence."""


def classify_slide(slide, width, height):
    shapes = slide["shapes"]
    counts = {
        kind: sum(s["kind"] == kind for s in shapes)
        for kind in ("image", "chart", "table", "text", "connector")
    }
    if counts["chart"]:
        layout, confidence, evidence = "results_chart", 0.9, "native_chart"
    elif counts["table"]:
        layout, confidence, evidence = "table", 0.85, "native_table"
    elif counts["connector"] >= 2:
        layout, confidence, evidence = "system_diagram", 0.65, "multiple_connectors"
    elif counts["image"]:
        image = max(
            (s for s in shapes if s["kind"] == "image"),
            key=lambda s: s["box"]["w"] * s["box"]["h"],
        )
        if image["box"]["w"] > width * 0.65:
            layout, confidence, evidence = "image_focus", 0.7, "wide_image"
        else:
            layout = "text_figure" if image["box"]["x"] > width * 0.4 else "figure_text"
            confidence, evidence = 0.6, "image_text_position"
    elif slide["index"] == 1 and counts["text"] <= 5:
        layout, confidence, evidence = (
            "title_cover",
            0.55,
            "first_slide_few_text_blocks",
        )
    else:
        layout, confidence, evidence = "bullets", 0.35, "text_only_fallback"
    return {"layout_type": layout, "confidence": confidence, "evidence": [evidence]}

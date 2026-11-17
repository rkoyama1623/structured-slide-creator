"""Exercise every public layout and block using small but real content."""

import pytest
from pptx import Presentation
from structured_slide_creator.generation import build_deck
from structured_slide_creator.generation.layouts import LAYOUTS
from structured_slide_creator.generation.blocks import BLOCK_TYPES
from structured_slide_creator.plan import normalize_plan


@pytest.mark.parametrize("theme", ["neutral", "academic"])
def test_all_layouts_and_blocks(tmp_path, theme):
    script = tmp_path / "custom.py"
    script.write_text(
        'from structured_slide_creator.generation.components import add_slide_title\ndef build(ctx, spec):\n    add_slide_title(ctx, spec["title"])\n'
    )
    extras = {
        "agenda": {"items": ["背景", "結論"]},
        "bullets": {"bullets": ["内容"]},
        "comparison": {
            "columns": [
                {"title": "A", "items": ["条件A"]},
                {"title": "B", "items": ["条件B"]},
            ]
        },
        "process_flow": {"steps": ["入力", "処理", "出力"]},
        "system_diagram": {
            "nodes": [
                {"id": "a", "label": "入力", "col": 0},
                {"id": "b", "label": "出力", "col": 1},
            ],
            "edges": [{"from": "a", "to": "b"}],
        },
        "algorithm": {"steps": ["手順一", "手順二"], "formulas": ["x = y + 1"]},
        "timeline": {
            "milestones": [
                {"date": "2026", "label": "試作"},
                {"date": "2027", "label": "評価"},
            ]
        },
        "roadmap": {
            "periods": ["一月", "二月"],
            "lanes": ["試作"],
            "bars": [{"lane": "試作", "from": 0, "to": 1, "label": "開発"}],
        },
        "experiment_setup": {"conditions": [["項目", "値"]]},
        "table": {"table": {"header": ["項目", "条件"], "rows": [["A", "未確認"]]}},
        "evaluation_matrix": {
            "options": ["A"],
            "criteria": ["精度"],
            "ratings": [["○"]],
        },
        "summary": {"points": ["確認結果"]},
        "custom_script": {"script": str(script)},
    }
    slides = [
        {"id": name, "layout": name, "title": name, **extras.get(name, {})}
        for name in LAYOUTS
    ]
    blocks = {
        "text": {"text": "文章"},
        "bullets": {"items": ["項目"]},
        "key_message": {"text": "主張"},
        "note": {"text": "注記"},
        "caption": {"text": "図の説明"},
        "formula": {"text": "x = 1"},
        "image": {"path": "missing-image.png"},
        "figure": {"label": "未提供の図"},
        "chart": {
            "kind": "bar",
            "categories": ["A"],
            "series": [{"name": "例", "values": [1]}],
        },
        "table": {"header": ["列"], "rows": [["値"]]},
        "matrix": {"options": ["A"], "criteria": ["軸"], "ratings": [["○"]]},
        "flow": {"steps": ["一", "二"]},
        "steps": {"steps": ["手順"]},
        "diagram": extras["system_diagram"],
        "timeline": extras["timeline"],
        "roadmap": extras["roadmap"],
        "compare": {
            "columns": [
                {"title": "A", "items": ["項目"]},
                {"title": "B", "items": ["項目"]},
            ]
        },
        "split": {
            "blocks": [{"type": "text", "text": "左"}, {"type": "text", "text": "右"}]
        },
        "empty": {},
    }
    assert set(blocks) == set(BLOCK_TYPES)
    slides += [
        {
            "id": f"block-{kind}",
            "layout": "free",
            "title": kind,
            "blocks": [{"type": kind, **spec}],
        }
        for kind, spec in blocks.items()
    ]
    result = build_deck(
        normalize_plan({"slides": slides}), out=tmp_path / "all.pptx", theme=theme
    )
    assert len(Presentation(result.pptx_path).slides) == len(LAYOUTS) + len(BLOCK_TYPES)

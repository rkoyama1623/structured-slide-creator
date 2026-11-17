from pathlib import Path
import json
import pytest
from pptx import Presentation

from structured_slide_creator.design.tokens import load_theme
from structured_slide_creator.design.rules import DesignRuleError, check_font_size
from structured_slide_creator.plan import load_plan, normalize_plan, validate_plan, save_plan
from structured_slide_creator.generation import build_deck
from structured_slide_creator.textmetrics import visual_length, wrapped_line_count

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("theme", ["neutral", "academic"])
def test_demo_build(theme, tmp_path):
    result = build_deck(
        load_plan(ROOT / "examples/demo_research.yaml"),
        out=tmp_path / "demo.pptx",
        theme=theme,
    )
    assert result.n_slides == 11
    assert result.warnings == []
    assert result.plan_issues == []
    prs = Presentation(result.pptx_path)
    assert len(prs.slides) == 11
    assert any(s.has_chart for slide in prs.slides for s in slide.shapes)
    assert any(s.has_table for slide in prs.slides for s in slide.shapes)
    manifest = json.loads(result.manifest_path.read_text())
    assert manifest["theme"] == theme
    assert manifest["slides"][6]["id"] == "results"
    from structured_slide_creator.review import check_pptx

    assert not [
        f
        for f in check_pptx(result.pptx_path, theme)
        if f.severity in ("must_fix", "should_fix")
    ]
    closing = "\n".join(s.text for s in prs.slides[-1].shapes if s.has_text_frame)
    assert closing.count("架空資料 A") == 1
    from pptx.oxml.ns import qn

    for slide in prs.slides:
        for shape in slide.shapes:
            assert all(
                ref.get("idx") == "0"
                for ref in shape._element.findall(f".//{qn('a:effectRef')}")
            )


def test_theme_inheritance_and_floors(tmp_path):
    neutral, academic = load_theme("neutral"), load_theme("academic")
    assert academic.lay("columns") == neutral.lay("columns") == 12
    assert academic.style("body").size > neutral.style("body").size
    assert neutral.color("accent") == "#2F5D8A"
    for role in ("body", "table_body", "caption", "footer"):
        with pytest.raises(DesignRuleError):
            check_font_size(academic, 7, role=role)
    (tmp_path / "base.yaml").write_text("extends: neutral\nname: base\n")
    (tmp_path / "child.yaml").write_text("extends: base\nname: child\n")
    assert (
        load_theme(str(tmp_path / "child.yaml")).style("body").size
        == neutral.style("body").size
    )
    (tmp_path / "base.yaml").write_text("extends: child\n")
    with pytest.raises(ValueError, match="circular"):
        load_theme(str(tmp_path / "base.yaml"))


def test_text_metrics():
    assert visual_length("研究") > visual_length("ab")
    assert wrapped_line_count("研究" * 20, 14, 1) > 2
    assert wrapped_line_count("a\n\nb", 14, 10) == 3


@pytest.mark.parametrize(
    "bad", [[], {"slides": "oops"}, {"slides": [1]}, {"meta": []}, {"slides": None}]
)
def test_bad_plan_shape(bad):
    with pytest.raises(TypeError):
        normalize_plan(bad)


def test_plan_validation_and_selection(tmp_path):
    plan = normalize_plan({"slides": [{"id": "a", "layout": "unknown"}, {"id": "a"}]})
    assert len([i for i in validate_plan(plan) if i.level == "error"]) == 2
    with pytest.raises(DesignRuleError):
        build_deck(plan, out=tmp_path / "bad.pptx")
    plan = load_plan(ROOT / "examples/demo_research.yaml")
    result = build_deck(plan, out=tmp_path / "one.pptx", only=["results"])
    assert result.n_slides == 1
    assert len(Presentation(result.pptx_path).slides) == 1
    with pytest.raises(DesignRuleError, match="未知"):
        build_deck(plan, out=tmp_path / "bad.pptx", only=["results", "missing"])


def test_relative_assets_and_notes(tmp_path, monkeypatch):
    from PIL import Image

    Image.new("RGB", (200, 100), "blue").save(tmp_path / "image.png")
    data = {
        "meta": {},
        "slides": [
            {
                "id": "figure",
                "layout": "image_focus",
                "title": "図",
                "image": "image.png",
                "speaker_notes": "日本語ノート",
            }
        ],
    }
    plan = normalize_plan(data)
    path = save_plan(plan, tmp_path / "plan.yaml")
    loaded = load_plan(path)
    monkeypatch.chdir("/")
    result = build_deck(loaded, out=tmp_path / "deck.pptx")
    prs = Presentation(result.pptx_path)
    assert any(s.shape_type == 13 for s in prs.slides[0].shapes)
    assert prs.slides[0].notes_slide.notes_text_frame.text == "日本語ノート"
    assert loaded.slides[0]["image"] == "image.png"


def test_table_overflow_and_roadmap(tmp_path):
    from structured_slide_creator.generation.deck import Deck
    from structured_slide_creator.generation.tables import make_table
    from structured_slide_creator.generation.diagram import draw_roadmap
    from structured_slide_creator.units import Box

    ctx = Deck().add_slide()
    with pytest.raises(DesignRuleError, match="収まりません"):
        make_table(ctx, Box(1, 1, 1, 0.5), ["見出し"], [["長い内容" * 40]])
    with pytest.raises(DesignRuleError, match="from/to"):
        draw_roadmap(
            ctx,
            Box(1, 1, 8, 4),
            ["一月", "二月"],
            ["lane"],
            [{"lane": "lane", "from": 1, "to": 0}],
        )


def test_aspect_and_custom_theme_manifest(tmp_path):
    import yaml
    from structured_slide_creator.cli import main

    theme = load_theme("academic")
    theme.raw["name"] = "custom-dark"
    theme.raw["colors"]["bg"] = "#122334"
    path = tmp_path / "custom.yaml"
    path.write_text(yaml.safe_dump(theme.raw))
    plan = normalize_plan(
        {
            "meta": {"aspect": "4:3"},
            "slides": [
                {
                    "layout": "bullets",
                    "title": "確認",
                    "bullets": [
                        {
                            "text": "一段目",
                            "children": [{"text": "二段目", "children": ["三段目"]}],
                        }
                    ],
                }
            ],
        }
    )
    result = build_deck(plan, out=tmp_path / "deck.pptx", theme=str(path))
    prs = Presentation(result.pptx_path)
    assert prs.slide_width / prs.slide_height == pytest.approx(4 / 3)
    assert str(prs.slides[0].background.fill.fore_color.rgb) == "122334"
    # Review remains possible after moving/deleting the original theme file.
    path.unlink()
    assert (
        main(["check", str(result.pptx_path), "--out", str(tmp_path / "check.json")])
        == 0
    )
    assert (
        json.loads(result.manifest_path.read_text())["theme_definition"]["name"]
        == "custom-dark"
    )

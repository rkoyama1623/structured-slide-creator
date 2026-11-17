import json

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt

from structured_slide_creator.review import check_pptx, review_pptx


def test_detect_review_problems(tmp_path):
    p = Presentation()
    slide = p.slides.add_slide(p.slide_layouts[6])
    tb = slide.shapes.add_textbox(Inches(-0.2), Inches(1), Inches(2), Inches(0.1))
    tb.text = "文字あふれの検出" * 20
    run = tb.text_frame.paragraphs[0].runs[0]
    run.font.size = Pt(7)
    run.font.color.rgb = RGBColor(240, 240, 240)
    for x in (3, 3.5):
        s = slide.shapes.add_textbox(Inches(x), Inches(1), Inches(2), Inches(1))
        s.text = "overlapping text"
    Image.new("RGB", (200, 100)).save(tmp_path / "pic.png")
    slide.shapes.add_picture(
        str(tmp_path / "pic.png"), Inches(1), Inches(3), Inches(1), Inches(1)
    )
    path = tmp_path / "problems.pptx"
    p.save(path)
    kinds = {f.kind for f in check_pptx(path)}
    assert {
        "outside_slide",
        "font_size",
        "contrast",
        "text_overflow",
        "overlap",
        "image_aspect",
    } <= kinds
    result = review_pptx(path, tmp_path / "report", render=False)
    assert result["visual_review"] == "not_requested"
    assert (tmp_path / "report/review.md").exists()
    assert json.loads((tmp_path / "report/images.json").read_text()) == []


def test_missing_renderer_still_writes_report(tmp_path, monkeypatch):
    from structured_slide_creator.rendering import RendererUnavailable
    from structured_slide_creator.review import report

    p = Presentation()
    p.slides.add_slide(p.slide_layouts[6])
    path = tmp_path / "deck.pptx"
    p.save(path)

    def unavailable(*args, **kwargs):
        raise RendererUnavailable("no renderer")

    monkeypatch.setattr(report, "render_pptx", unavailable)
    result = report.review_pptx(path, tmp_path / "report")
    assert result["visual_review"] == "unavailable"
    assert result["notes"] == ["no renderer"]
    assert (tmp_path / "report/review.json").exists()


def test_review_hash_binding_pending_and_drift(tmp_path, monkeypatch):
    import hashlib

    from structured_slide_creator.rendering.base import RenderResult
    from structured_slide_creator.review import report, verify_review_bindings

    p = Presentation()
    p.slides.add_slide(p.slide_layouts[6])
    path = tmp_path / "deck.pptx"
    p.save(path)
    source = tmp_path / "source.py"
    source.write_text("pass\n")
    image = tmp_path / "slide01.png"
    Image.new("RGB", (50, 30), "white").save(image)
    monkeypatch.setattr(
        report,
        "render_pptx",
        lambda *a, **k: RenderResult([image], "fake", "approximate"),
    )
    result = review_pptx(path, tmp_path / "review", sources=[source])
    assert result["pptx_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert (
        result["images"][0]["sha256"] == hashlib.sha256(image.read_bytes()).hexdigest()
    )
    assert result["source_review"] == "pending" and result["visual_review"] == "pending"
    assert (
        result["artifact_status"] == "stable" and verify_review_bindings(result) == []
    )
    source.write_text("changed\n")
    assert any(
        "changed" in d and "source.py" in d for d in verify_review_bindings(result)
    )
    image.unlink()
    assert any("missing" in d for d in verify_review_bindings(result))


def test_change_during_render_marks_review_stale(tmp_path, monkeypatch):
    from structured_slide_creator.rendering.base import RenderResult
    from structured_slide_creator.review import report

    p = Presentation()
    p.slides.add_slide(p.slide_layouts[6])
    path = tmp_path / "deck.pptx"
    p.save(path)

    def changed(*a, **k):
        path.write_bytes(path.read_bytes() + b"changed")
        return RenderResult([], "fake", "approximate")

    monkeypatch.setattr(report, "render_pptx", changed)
    result = review_pptx(path, tmp_path / "review")
    assert result["artifact_status"] == "stale" and result["visual_review"] == "stale"
    assert result["pptx_sha256"] != result["pptx_sha256_after"]
    assert (
        json.loads((tmp_path / "review/review.json").read_text())["artifact_status"]
        == "stale"
    )

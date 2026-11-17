import json
import yaml
import pytest
from pptx import Presentation
from pptx.util import Inches
from PIL import Image
from structured_slide_creator.analysis import analyze_directory, extract_pptx
from structured_slide_creator.analysis.catalog import merge_catalog, tune_catalog
from structured_slide_creator.analysis.sanitize import validate_sanitized


def test_analysis_privacy_and_catalog(tmp_path):
    root = tmp_path / "raw"
    root.mkdir()
    p = Presentation()
    slide = p.slides.add_slide(p.slide_layouts[6])
    tb = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(1))
    tb.text = "株式会社秘密情報 SECRET-918273"
    tb.name = "SECRET-SHAPE"
    tb.text_frame.paragraphs[0].runs[0].font.name = "SECRET-FONT"
    Image.new("RGB", (50, 50), "#1A2B3C").save(root / "logo.png")
    slide.shapes.add_picture(str(root / "logo.png"), 0, 0, Inches(0.4), Inches(0.4))
    p.save(root / "SECRET-FILENAME.pptx")
    paths = analyze_directory(root, tmp_path / "sanitized")
    text = paths[0].read_text()
    assert all(
        secret not in text
        for secret in ("秘密", "SECRET", "SECRET-FILENAME", "1A2B3C", str(root))
    )
    deck = json.loads(text)
    validate_sanitized(deck)
    assert deck["slides"][0]["shapes"][1]["inherit"] is False
    assert (
        deck["slides"][0]["shapes"][0]["brand_flags"][0]["needs_human_review"] is True
    )
    assert list((tmp_path / "sanitized/wireframes").rglob("*.png"))
    catalog = tmp_path / "catalog.yaml"
    merge_catalog(catalog, [deck])
    entry = yaml.safe_load(catalog.read_text())["entries"][0]
    tune_catalog(catalog, entry["id"], "accepted", "採用")
    merge_catalog(catalog, [deck])
    entries = yaml.safe_load(catalog.read_text())["entries"]
    assert len(entries) == 1
    assert entries[0]["status"] == "accepted"
    assert entries[0]["comment"] == "採用"
    with pytest.raises(ValueError):
        validate_sanitized(extract_pptx(root / "SECRET-FILENAME.pptx"))


def test_explicit_input_required(tmp_path):
    with pytest.raises(ValueError):
        analyze_directory(tmp_path / "missing", tmp_path / "out")
    with pytest.raises(ValueError, match="PPTX"):
        analyze_directory(tmp_path, tmp_path / "out")

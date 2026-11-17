from pathlib import Path
import pytest
from PIL import Image
from pptx import Presentation
from structured_slide_creator.generation import build_deck
from structured_slide_creator.plan import load_plan
from structured_slide_creator.rendering import available_renderers, render_pptx

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(
    "libreoffice" not in available_renderers(), reason="LibreOffice not available"
)
def test_real_render_selected_slides(tmp_path):
    build = build_deck(
        load_plan(ROOT / "examples/demo_research.yaml"), out=tmp_path / "demo.pptx"
    )
    result = render_pptx(
        build.pptx_path,
        tmp_path / "slides",
        renderer="libreoffice",
        slides=[4, 7, 9],
        width=640,
    )
    assert [p.name for p in result.images] == [
        "slide04.png",
        "slide07.png",
        "slide09.png",
    ]
    assert result.fidelity == "approximate"
    for path in result.images:
        with Image.open(path) as im:
            assert im.width == 640
            assert 359 <= im.height <= 361


def test_render_reject_invalid_selection_and_size(tmp_path):
    p = Presentation()
    p.slides.add_slide(p.slide_layouts[6])
    path = tmp_path / "deck.pptx"
    p.save(path)
    for slides in ([], [0], [2]):
        with pytest.raises(ValueError):
            render_pptx(path, tmp_path / "slides", slides=slides)
    with pytest.raises(ValueError):
        render_pptx(path, tmp_path / "slides", width=0)

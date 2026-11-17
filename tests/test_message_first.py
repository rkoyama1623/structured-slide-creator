"""Message planning, independent layout reservations and native-only generation."""

from pathlib import Path

import pytest
import yaml
from pptx import Presentation

from structured_slide_creator.cli import main
from structured_slide_creator.message_first import (
    build_layout,
    layout_to_markdown,
    load_layout,
    load_story,
    story_to_markdown,
    validate_layout,
    validate_story,
)
from structured_slide_creator.message_first.common import Document

ROOT = Path(__file__).resolve().parents[1]


def dump(path, data):
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def story_data():
    return {
        "message": "先に概念を説明してから，提案の意味を伝える。",
        "concepts": [
            {
                "id": "c",
                "label": "状態の分類",
                "definition": "説明用に状態名をまとめた分類。",
            }
        ],
        "assets": [
            {"id": "fig", "path": "not-created.svg", "role": "提案の関係を示す"}
        ],
        "sections": [
            {
                "id": "first",
                "claim": "説明用の状態名を定義する。",
                "body": "状態の分類とは説明用の状態名をまとめたものである。",
                "introduces": ["c"],
            },
            {
                "id": "later",
                "claim": "定義した状態名に説明文を付ける。",
                "body": "前節の状態の分類を用い，短い説明文を付ける。",
                "depends_on": ["first"],
                "uses": ["c"],
                "evidence": ["fig"],
            },
        ],
    }


def layout_data(story=None):
    result = {
        "page": {"width_mm": 297, "height_mm": 420},
        "typography": {"label_pt": 16},
        "pages": [
            {
                "id": "p",
                "reading_order": ["intro", "diagram"],
                "regions": [
                    {
                        "id": "intro",
                        "kind": "body",
                        "label": "導入",
                        "box_mm": [10, 10, 277, 40],
                        "sections": ["first"],
                    },
                    {
                        "id": "diagram",
                        "kind": "figure",
                        "label": "提案図の予約",
                        "box_mm": [10, 60, 277, 150],
                        "sections": ["later"],
                        "assets": ["fig"],
                        "purpose": "定義した概念に基づく提案を説明する。",
                    },
                ],
            }
        ],
    }
    if story:
        result["story"] = story
    return result


def test_story_prose_concepts_evidence_and_relative_paths(tmp_path, monkeypatch):
    folder = tmp_path / "plans"
    folder.mkdir()
    path = dump(folder / "story.yaml", story_data())
    doc = load_story(path)
    assert validate_story(doc) == []
    md = story_to_markdown(doc)
    for value in [
        doc.data["message"],
        doc.data["sections"][0]["body"],
        "Requires earlier sections",
        "説明用に状態名をまとめた分類。",
        "提案の関係を示す",
    ]:
        assert value in md
    monkeypatch.chdir(tmp_path)
    assert doc.resolve(doc.data["assets"][0]["path"]) == folder / "not-created.svg"
    assert str(folder / "not-created.svg") in md


@pytest.mark.parametrize(
    "mutate,phrase",
    [
        (lambda d: d["sections"].reverse(), "earlier"),
        (lambda d: d["sections"][1].update(uses=["missing"]), "unknown uses"),
        (lambda d: d["sections"][1].update(evidence=["missing"]), "unknown evidence"),
        (
            lambda d: d["sections"][1].update(depends_on=["missing"]),
            "unknown depends_on",
        ),
        (lambda d: d["sections"][1].update(id="first"), "duplicate id"),
        (lambda d: d.update(message=" "), "message is required"),
        (lambda d: d["sections"][0].update(uses=["c"]), "earlier section"),
        (lambda d: d["sections"][1].update(introduces=["c"]), "more than once"),
    ],
)
def test_story_errors(mutate, phrase):
    data = story_data()
    mutate(data)
    assert any(phrase in i.message for i in validate_story(Document(data)))


def test_linked_layout_native_only_and_no_prose_insertion(tmp_path, monkeypatch):
    dump(tmp_path / "story.yaml", story_data())
    path = dump(tmp_path / "layout.yaml", layout_data("story.yaml"))
    doc = load_layout(path)
    assert validate_layout(doc) == []
    monkeypatch.chdir("/")
    import PIL.Image

    monkeypatch.setattr(
        PIL.Image, "open", lambda *a, **k: pytest.fail("wireframe must not load images")
    )
    out = build_layout(doc, tmp_path / "layout.pptx")
    prs = Presentation(out)
    assert len(prs.slides) == 1
    assert prs.slide_width / 36000 == pytest.approx(297)
    assert prs.slide_height / 36000 == pytest.approx(420)
    assert not any(sh.shape_type == 13 for sh in prs.slides[0].shapes)
    labels = "\n".join(sh.text for sh in prs.slides[0].shapes if sh.has_text_frame)
    assert "提案図の予約" in labels and "fig" in labels
    assert doc.story.data["message"] not in labels
    assert all(s["body"] not in labels for s in doc.story.data["sections"])
    md = layout_to_markdown(doc)
    assert (
        "area=41550" in md
        and "定義した状態名に説明文を付ける。" in md
        and "定義した概念に基づく提案を説明する。" in md
    )


def test_reordered_layout_context_errors_and_unmapped_warning(tmp_path):
    dump(tmp_path / "story.yaml", story_data())
    data = layout_data("story.yaml")
    data["pages"][0]["reading_order"].reverse()
    doc = load_layout(dump(tmp_path / "layout.yaml", data))
    issues = validate_layout(doc)
    assert any(i.level == "error" and "before" in i.message for i in issues)
    data["pages"][0]["regions"] = data["pages"][0]["regions"][1:]
    data["pages"][0]["reading_order"] = ["diagram"]
    doc = load_layout(dump(tmp_path / "layout.yaml", data))
    issues = validate_layout(doc)
    assert any(i.level == "warning" and "unmapped section" in i.message for i in issues)


@pytest.mark.parametrize(
    "mutate,phrase",
    [
        (
            lambda d: d["pages"][0]["regions"][0].update(box_mm=[-1, 0, 100, 40]),
            "outside",
        ),
        (
            lambda d: d["pages"][0]["regions"][0].update(box_mm=[0, 0, 0, 40]),
            "positive",
        ),
        (
            lambda d: d["pages"][0].update(reading_order=["intro", "intro"]),
            "duplicate reading_order",
        ),
        (
            lambda d: d["pages"][0].update(reading_order=["unknown"]),
            "unknown reading_order",
        ),
        (
            lambda d: d["pages"][0]["regions"][0].update(sections=["unknown"]),
            "unknown sections",
        ),
        (
            lambda d: d["pages"][0]["regions"][0].update(assets=["unknown"]),
            "unknown assets",
        ),
        (
            lambda d: d["pages"][0]["regions"][0].update(label="長い文字" * 100),
            "does not fit",
        ),
    ],
)
def test_layout_validation(tmp_path, mutate, phrase):
    dump(tmp_path / "story.yaml", story_data())
    data = layout_data("story.yaml")
    mutate(data)
    issues = validate_layout(load_layout(dump(tmp_path / "layout.yaml", data)))
    assert any(phrase in i.message for i in issues)


def test_nested_and_colliding_geometry_and_multiple_pages(tmp_path):
    data = {
        "page": {"width_mm": 338.6667, "height_mm": 190.5},
        "typography": {"label_pt": 12},
        "pages": [
            {
                "id": "one",
                "regions": [
                    {
                        "id": "outer",
                        "kind": "figure",
                        "label": "outer",
                        "box_mm": [5, 5, 200, 100],
                    },
                    {
                        "id": "inner",
                        "kind": "note",
                        "label": "inner",
                        "box_mm": [10, 30, 80, 25],
                    },
                ],
            }
        ],
    }
    doc = load_layout(dump(tmp_path / "layout.yaml", data))
    assert not any("overlap" in i.message for i in validate_layout(doc))
    data["pages"][0]["regions"][1]["box_mm"] = [180, 50, 80, 40]
    doc = load_layout(dump(tmp_path / "layout.yaml", data))
    assert any("overlap" in i.message for i in validate_layout(doc))
    data["pages"].append(
        {
            "id": "two",
            "regions": [
                {
                    "id": "outer",
                    "kind": "body",
                    "label": "second",
                    "box_mm": [5, 5, 200, 100],
                }
            ],
        }
    )
    out = build_layout(
        load_layout(dump(tmp_path / "layout.yaml", data)), tmp_path / "multi.pptx"
    )
    assert len(Presentation(out).slides) == 2


@pytest.mark.parametrize(
    "command,payload",
    [
        ("story", {"message": True, "sections": []}),
        ("story", {"message": "x", "sections": [{"id": 4}]}),
        ("story", {"message": "x", "sections": [{"id": "a", "uses": "wrong"}]}),
        ("layout", {"page": {"width_mm": True, "height_mm": 420}}),
        ("layout", {"page": {"width_mm": float("nan"), "height_mm": 420}}),
        (
            "layout",
            {
                "page": {"width_mm": 297, "height_mm": 420},
                "pages": [{"regions": [{"box_mm": [1, 2, 3]}]}],
            },
        ),
        ("layout", {"page": {"width_mm": 297, "height_mm": 420}, "pages": "wrong"}),
    ],
)
def test_cli_friendly_type_errors(tmp_path, capsys, command, payload):
    path = dump(tmp_path / "bad.yaml", payload)
    assert main([command, "check", str(path)]) == 2
    assert "Traceback" not in capsys.readouterr().err


def test_new_cli_examples_and_geometry_error_exit(tmp_path, capsys):
    for command, name in [
        ("story", "message_first_story.yaml"),
        ("layout", "message_first_layout.yaml"),
    ]:
        source = ROOT / "examples" / name
        assert main([command, "check", str(source)]) == 0
        assert (
            main([command, "md", str(source), "--out", str(tmp_path / f"{command}.md")])
            == 0
        )
    assert (
        main(
            [
                "layout",
                "build",
                str(ROOT / "examples/message_first_layout.yaml"),
                "--out",
                str(tmp_path / "example.pptx"),
            ]
        )
        == 0
    )
    assert main(["story", "check", str(dump(tmp_path / "missing.yaml", {}))]) == 1
    data = layout_data()
    data["pages"][0]["regions"][0]["box_mm"] = [0, 0, -10, 40]
    path = dump(tmp_path / "bad.yaml", data)
    assert (
        main(["layout", "build", str(path), "--out", str(tmp_path / "bad.pptx")]) == 1
    )
    assert not (tmp_path / "bad.pptx").exists()
    weird = tmp_path / "bad.txt"
    weird.write_text("{}")
    assert main(["story", "check", str(weird)]) == 2
    assert "Traceback" not in capsys.readouterr().err


def test_unrepresentable_integer_is_friendly_type_error(tmp_path, capsys):
    data = layout_data()
    data["page"]["width_mm"] = 10**1000
    path = dump(tmp_path / "large.yaml", data)
    assert main(["layout", "check", str(path)]) == 2
    assert "Traceback" not in capsys.readouterr().err

import json
from pathlib import Path

import pytest

from structured_slide_creator.cli import main
from structured_slide_creator.skills_sync import sync_skills

ROOT = Path(__file__).resolve().parents[1]


def test_cli_end_to_end(tmp_path, capsys):
    plan = str(ROOT / "examples/demo_research.yaml")
    deck = str(tmp_path / "demo.pptx")
    assert main(["plan", "check", plan]) == 0
    assert main(["plan", "md", plan, "--out", str(tmp_path / "plan.md")]) == 0
    assert main(["build", plan, "--out", deck, "--only", "results"]) == 0
    assert main(["check", deck, "--out", str(tmp_path / "check.json")]) == 0
    assert main(["review", deck, "--no-render"]) == 0
    assert main(["themes"]) == 0
    capsys.readouterr()
    assert main(["doctor"]) == 0
    assert "renderers" in json.loads(capsys.readouterr().out)
    catalog = str(tmp_path / "catalog.yaml")
    assert main(["catalog", "export", "--out", catalog]) == 0
    assert main(["catalog", "export", "--out", catalog]) == 2


def test_cli_bad_inputs(tmp_path, capsys):
    invalid = tmp_path / "bad.yaml"
    invalid.write_text("slides: [42]")
    assert main(["build", str(invalid), "--out", str(tmp_path / "out.pptx")]) == 2
    assert "Traceback" not in capsys.readouterr().err
    invalid.write_text("slides: [{layout: nope}]")
    assert main(["plan", "check", str(invalid)]) == 1
    with pytest.raises(SystemExit) as exc:
        main(["analyze"])
    assert exc.value.code == 2


def test_skills_drift(tmp_path):
    expected_skills = [
        p
        for p in (ROOT / "skills").rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    ]
    references = [
        "docs/HELPERS.md",
        "docs/MESSAGE_FIRST.md",
        "examples/demo_research.yaml",
        "examples/message_first_story.yaml",
        "examples/message_first_layout.yaml",
    ]
    assert len(sync_skills(tmp_path, check=True)) == 2 * len(expected_skills) + len(
        references
    )
    sync_skills(tmp_path)
    assert sync_skills(tmp_path, check=True) == []
    for base in [".agents/skills", ".claude/skills"]:
        for source in expected_skills:
            assert (
                tmp_path / base / source.relative_to(ROOT / "skills")
            ).read_bytes() == source.read_bytes()
    for reference in references:
        assert (tmp_path / reference).read_bytes() == (ROOT / reference).read_bytes()
    target = tmp_path / ".agents/skills/slides-create/SKILL.md"
    target.write_text("drift")
    assert sync_skills(tmp_path, check=True) == [str(target)]
    sync_skills(tmp_path)
    assert sync_skills(tmp_path, check=True) == []

"""Copy canonical project skills and detect missing/modified copies."""

from pathlib import Path

from .resources import asset_root


def sync_skills(root=".", *, check=False):
    root = Path(root)
    source = asset_root() / "skills"
    files = sorted(
        p for p in source.rglob("*") if p.is_file() and "__pycache__" not in p.parts
    )
    if not files:
        raise ValueError("canonical skills are missing")
    differences = []
    for base in (".agents/skills", ".claude/skills"):
        for path in files:
            target = root / base / path.relative_to(source)
            if not target.exists() or target.read_bytes() != path.read_bytes():
                differences.append(str(target))
                if not check:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(path.read_bytes())
    # Include the local references needed by installed skills.
    for relative in (
        "docs/HELPERS.md",
        "docs/MESSAGE_FIRST.md",
        "examples/demo_research.yaml",
        "examples/message_first_story.yaml",
        "examples/message_first_layout.yaml",
    ):
        reference = asset_root() / relative
        target = root / relative
        if reference.resolve() != target.resolve() and (
            not target.exists() or target.read_bytes() != reference.read_bytes()
        ):
            differences.append(str(target))
            if not check:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(reference.read_bytes())
    return differences

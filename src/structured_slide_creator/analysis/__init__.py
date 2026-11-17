"""Explicit-input local analysis, emitting only sanitized structures."""

from pathlib import Path
import json
from .extract import extract_pptx
from .sanitize import deck_id, sanitize_deck, wireframe


def analyze_directory(input_dir, out_dir):
    root, out = Path(input_dir).resolve(), Path(out_dir).resolve()
    if not root.is_dir():
        raise ValueError("--input must be an existing directory")
    paths = sorted(
        p
        for p in root.rglob("*")
        if p.suffix.lower() == ".pptx" and not p.name.startswith("~$")
    )
    if not paths:
        raise ValueError("指定ディレクトリに PPTX がありません")
    results = []
    for path in paths:
        deck = sanitize_deck(extract_pptx(path))
        did = deck_id(deck)
        target = out / f"{did}.json"
        out.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(deck, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        for slide in deck["slides"]:
            wireframe(
                deck, slide, out / "wireframes" / did / f"slide{slide['index']:02d}.png"
            )
        results.append(target)
    return results


__all__ = ["analyze_directory", "extract_pptx", "sanitize_deck"]

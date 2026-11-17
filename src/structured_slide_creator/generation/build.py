"""plan → PPTX のビルダ（データ駆動）。

スライド単体の再生成にも対応する:
  - `only` を指定すると、そのスライドだけを含む PPTX を作る（確認用の速いループ）
  - 既定は全枚数を作り直す（plan が唯一の正なので差分管理が不要）
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from copy import deepcopy
from pathlib import Path
from typing import Iterable, Sequence

from ..design.rules import DesignRuleError
from ..design.tokens import Theme, load_theme
from ..plan.schema import DeckPlan, errors, validate_plan
from .deck import Deck, DeckMeta
from .layouts import build_slide


@dataclass
class BuildResult:
    pptx_path: Path
    manifest_path: Path | None
    theme: str
    slides: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    plan_issues: list[str] = field(default_factory=list)

    @property
    def n_slides(self) -> int:
        return len(self.slides)


def _meta_from_plan(plan: DeckPlan) -> DeckMeta:
    m = plan.meta
    return DeckMeta(
        title=str(m.get("title", "")),
        subtitle=str(m.get("subtitle", "")),
        author=str(m.get("author", "")),
        affiliation=str(m.get("affiliation", "")),
        date=str(m.get("date", "")),
        event=str(m.get("event", "")),
        footer_text=str(m.get("footer_text", "")),
    )


def build_deck(
    plan: DeckPlan,
    *,
    out: str | Path,
    theme: str | Theme | None = None,
    only: Sequence[str | int] | None = None,
    strict_plan: bool = True,
    write_manifest: bool = True,
) -> BuildResult:
    issues = validate_plan(plan)
    hard = errors(issues)
    if hard and strict_plan:
        raise DesignRuleError(
            "plan に誤りがあります:\n  " + "\n  ".join(str(i) for i in hard)
        )

    theme_obj = theme if isinstance(theme, Theme) else load_theme(theme or plan.theme_name)
    if plan.meta.get("aspect"):
        theme_obj = deepcopy(theme_obj)
        theme_obj.raw["slide"] = {"aspect": plan.meta["aspect"]}
    deck = Deck(theme_obj, _meta_from_plan(plan))

    selected = deepcopy(_select(plan.slides, only))
    if plan.source_dir:
        _resolve_assets(selected, plan.source_dir)
    built: list[dict] = []
    for spec in selected:
        ctx = deck.add_slide(section=str(spec.get("section", "")), slide_id=str(spec.get("id")))
        try:
            build_slide(ctx, spec)
        except DesignRuleError as exc:
            raise DesignRuleError(f"[{spec.get('id')}] {spec.get('layout')}: {exc}") from exc
        built.append({
            "index": ctx.index + 1,
            "id": ctx.slide_id,
            "layout": spec.get("layout"),
            "section": ctx.section,
            "title": ctx.title,
            "lead": ctx.lead,
        })
    deck.finalize()
    out_path = deck.save(out)

    manifest_path = None
    if write_manifest:
        manifest_path = out_path.with_suffix(".manifest.json")
        manifest_path.write_text(
            json.dumps({
                "pptx": out_path.name,
                "theme": theme_obj.name,
                "theme_definition": theme_obj.raw,
                "meta": plan.meta,
                "slides": built,
                "warnings": deck.warnings,
                "plan_issues": [str(i) for i in issues],
            }, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    return BuildResult(
        pptx_path=out_path,
        manifest_path=manifest_path,
        theme=theme_obj.name,
        slides=built,
        warnings=list(deck.warnings),
        plan_issues=[str(i) for i in issues],
    )


def _select(slides: list[dict], only: Iterable[str | int] | None) -> list[dict]:
    if not only:
        return slides
    wanted = {str(x) for x in only}
    matched = set()
    out = []
    for i, s in enumerate(slides, start=1):
        if str(i) in wanted or str(s.get("id")) in wanted:
            matched.update(wanted & {str(i), str(s.get("id"))})
            out.append(s)
    if wanted - matched:
        raise DesignRuleError(f"--only に未知のスライドがあります: {sorted(wanted - matched)}")
    if not out:
        raise DesignRuleError(f"--only {sorted(wanted)} に一致するスライドがありません")
    return out


def _resolve_assets(value, root: Path):
    """Resolve only asset fields, without changing plan serialization or process cwd."""
    if isinstance(value, list):
        for item in value:
            _resolve_assets(item, root)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key in ("image", "path", "script") and isinstance(item, str) and item:
                path = Path(item).expanduser()
                if not path.is_absolute():
                    value[key] = str(root / path)
            else:
                _resolve_assets(item, root)

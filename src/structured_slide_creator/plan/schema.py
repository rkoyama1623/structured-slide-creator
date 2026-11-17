"""スライド構成計画（plan）の検証。

plan は生成前に人間がレビューできる YAML/Markdown の成果物であり、
「何を伝えるか」を決める唯一の入力。PPTX はここから機械的に作られる。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from pathlib import Path

META_KEYS = {
    "title", "subtitle", "author", "affiliation", "date", "event",
    "theme", "aspect", "footer_text", "audience", "purpose", "duration_min", "language",
}
COMMON_SLIDE_KEYS = {
    "id", "section", "layout", "title", "lead", "key_message", "notes",
    "speaker_notes", "references", "headings", "ratios", "divider", "note",
    "caption", "status", "comment",
}


@dataclass
class PlanIssue:
    level: str          # error | warning
    where: str
    message: str

    def __str__(self) -> str:  # pragma: no cover - 表示用
        return f"[{self.level}] {self.where}: {self.message}"


@dataclass
class DeckPlan:
    meta: dict[str, Any] = field(default_factory=dict)
    slides: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    source_dir: Path | None = None

    @property
    def theme_name(self) -> str:
        return str(self.meta.get("theme") or "neutral")

    def slide_by_id(self, slide_id: str) -> dict | None:
        for s in self.slides:
            if str(s.get("id")) == str(slide_id):
                return s
        return None


def normalize_plan(data: dict) -> DeckPlan:
    if not isinstance(data, dict):
        raise TypeError("plan は辞書（YAML のマッピング）である必要があります")
    if not isinstance(data.get("meta", {}), dict):
        raise TypeError("meta はマッピングである必要があります")
    if not isinstance(data.get("slides", []), list) or any(not isinstance(s, dict) for s in data.get("slides", [])):
        raise TypeError("slides はマッピングのリストである必要があります")
    meta = dict(data.get("meta") or {})
    slides = [dict(s) for s in data.get("slides", [])]
    for i, s in enumerate(slides, start=1):
        s.setdefault("id", f"slide{i:02d}")
        s.setdefault("layout", "bullets")
    return DeckPlan(meta=meta, slides=slides, raw=data)


def validate_plan(plan: DeckPlan) -> list[PlanIssue]:
    """構成の妥当性を検査する。error が 1 件でもあればビルドしない。"""
    from ..generation.layouts import LAYOUTS

    issues: list[PlanIssue] = []
    if not plan.slides:
        issues.append(PlanIssue("error", "slides", "スライドが 1 枚もありません"))

    for key in plan.meta:
        if key not in META_KEYS:
            issues.append(PlanIssue("warning", "meta", f"未知のメタ情報キー {key!r}"))

    if plan.meta.get("aspect", "16:9") not in ("16:9", "4:3"):
        issues.append(PlanIssue("error", "meta.aspect", "aspect は16:9または4:3を指定してください"))
    seen_ids: set[str] = set()
    for i, s in enumerate(plan.slides, start=1):
        where = f"slides[{i}] ({s.get('id')})"
        sid = str(s.get("id"))
        if sid in seen_ids:
            issues.append(PlanIssue("error", where, f"id が重複しています: {sid}"))
        seen_ids.add(sid)

        layout = str(s.get("layout", ""))
        if layout not in LAYOUTS:
            issues.append(PlanIssue(
                "error", where,
                f"未知のレイアウト {layout!r}。利用可能: {sorted(LAYOUTS)}"
            ))
            continue

        spec = LAYOUTS[layout]
        allowed = COMMON_SLIDE_KEYS | set(spec.keys) | {
            "left", "right", "blocks", "bullets", "body", "figure", "chart", "table",
            "items", "columns", "steps", "nodes", "edges", "groups", "rows", "cols",
            "milestones", "periods", "lanes", "bars", "options", "criteria", "ratings",
            "comments", "conditions", "findings", "findings_heading", "points",
            "next_steps", "next_heading", "image", "script", "mirror", "number",
            "formulas", "current", "message", "contact", "references_heading",
            "subtitle", "author", "affiliation", "date", "event", "direction",
            "problem", "solution", "numbered", "axis_label", "y_title", "x_title",
        }
        for key in s:
            if key not in allowed:
                issues.append(PlanIssue(
                    "warning", where,
                    f"レイアウト {layout!r} では使われないキー {key!r}"
                ))

        if layout not in ("title_cover", "section_divider", "closing") and not s.get("title"):
            issues.append(PlanIssue("warning", where, "title が空です"))
        if layout == "comparison" and len(s.get("columns") or []) < 2:
            issues.append(PlanIssue("error", where, "comparison には columns が 2 つ以上必要です"))
        if layout == "results_chart" and not (s.get("chart") or s.get("figure")):
            issues.append(PlanIssue("warning", where, "chart が未指定です（図のプレースホルダになります）"))
        if layout == "custom_script" and not s.get("script"):
            issues.append(PlanIssue("error", where, "custom_script には script パスが必要です"))

    # 構成全体の素直さ（同じレイアウトが続きすぎないか）
    run, prev = 1, None
    for s in plan.slides:
        cur = s.get("layout")
        if cur == prev:
            run += 1
            if run == 4:
                issues.append(PlanIssue(
                    "warning", f"slides({s.get('id')})",
                    f"同じレイアウト {cur!r} が 4 枚以上続いています。"
                    f" 図解・比較・表などに変化を付けることを検討してください。"
                ))
        else:
            run = 1
        prev = cur
    return issues


def errors(issues: list[PlanIssue]) -> list[PlanIssue]:
    return [i for i in issues if i.level == "error"]

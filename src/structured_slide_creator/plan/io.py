"""plan の入出力（YAML / JSON / Markdown 要約）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .schema import DeckPlan, normalize_plan


def load_plan(path: str | Path) -> DeckPlan:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    data = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    plan = normalize_plan(data if data is not None else {})
    plan.source_dir = path.resolve().parent
    return plan


def save_plan(plan: DeckPlan, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"meta": plan.meta, "slides": plan.slides}
    if path.suffix.lower() == ".json":
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        path.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=100),
            encoding="utf-8",
        )
    return path


def plan_to_markdown(plan: DeckPlan) -> str:
    """構成レビュー用の Markdown 要約（人が読んで承認するための形）。"""
    meta = plan.meta
    lines = [f"# {meta.get('title', '(無題)')}", ""]
    for key, label in (("subtitle", "サブタイトル"), ("audience", "想定聴衆"),
                       ("purpose", "目的"), ("event", "場"), ("date", "日付"),
                       ("theme", "テーマ"), ("duration_min", "持ち時間(分)")):
        if meta.get(key):
            lines.append(f"- **{label}**: {meta[key]}")
    lines += ["", f"全 {len(plan.slides)} 枚", ""]
    section = None
    for i, s in enumerate(plan.slides, start=1):
        if s.get("section") and s["section"] != section:
            section = s["section"]
            lines += [f"## {section}", ""]
        lines.append(f"### {i}. {s.get('title', '(no title)')}  `{s.get('layout')}`")
        if s.get("lead") or s.get("key_message"):
            lines.append(f"- **キーメッセージ**: {s.get('lead') or s.get('key_message')}")
        body_bits = _content_summary(s)
        if body_bits:
            lines.append(f"- **内容**: {body_bits}")
        if s.get("references"):
            lines.append(f"- **出典**: {len(s['references'])} 件")
        lines.append("")
    return "\n".join(lines)


def _content_summary(s: dict[str, Any]) -> str:
    bits: list[str] = []
    if s.get("bullets"):
        bits.append(f"箇条書き {len(s['bullets'])} 項目")
    for key, label in (("steps", "手順"), ("nodes", "ノード"), ("milestones", "時点"),
                       ("options", "比較対象"), ("points", "要点"), ("columns", "比較列")):
        if s.get(key):
            bits.append(f"{label} {len(s[key])} 件")
    if s.get("chart"):
        kind = s["chart"].get("kind", "chart") if isinstance(s["chart"], dict) else "chart"
        bits.append(f"グラフ({kind})")
    if s.get("table") or s.get("conditions"):
        bits.append("表")
    if s.get("image"):
        bits.append("画像")
    if s.get("figure"):
        bits.append("図")
    return " / ".join(bits)

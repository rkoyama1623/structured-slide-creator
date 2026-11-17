"""Command-line entry point. Success=0, findings/validation=1, execution failure=2."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from . import __version__
from .design.tokens import available_themes, load_theme, theme_from_dict
from .generation import build_deck
from .plan import errors, load_plan, plan_to_markdown, validate_plan
from .rendering import available_renderers, render_pptx
from .review import check_pptx, review_pptx


def _parser():
    p = argparse.ArgumentParser(
        prog="structured-slide-creator", description="編集可能なPowerPointをplan YAMLから生成"
    )
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="planからPPTXを生成")
    b.add_argument("plan", type=Path)
    b.add_argument("--out", "-o", required=True, type=Path)
    b.add_argument("--theme")
    b.add_argument(
        "--only",
        nargs="+",
        help="スライドIDまたは1始まりの番号（指定ページだけのPPTX）",
    )
    b.add_argument("--render", action="store_true")
    r = sub.add_parser("render", help="PPTXをPNGへ変換")
    r.add_argument("pptx", type=Path)
    r.add_argument("--out", "-o", required=True, type=Path)
    r.add_argument(
        "--renderer", choices=["auto", "powerpoint", "libreoffice"], default="auto"
    )
    r.add_argument("--width", type=int, default=1600)
    r.add_argument("--slides", nargs="+", type=int)
    for name in ("check", "review"):
        c = sub.add_parser(
            name, help="構造検査" if name == "check" else "構造検査と画像出力"
        )
        c.add_argument("pptx", type=Path)
        c.add_argument("--theme", help="省略時は隣接manifest、なければneutral")
        c.add_argument("--out", "-o", type=Path)
        if name == "review":
            c.add_argument("--no-render", action="store_true")
            c.add_argument(
                "--sources",
                nargs="+",
                type=Path,
                help="explicit source files to hash; source review stays pending",
            )
            c.add_argument(
                "--renderer",
                choices=["auto", "powerpoint", "libreoffice"],
                default="auto",
            )
    plan = sub.add_parser("plan", help="構成案を検証・Markdown化").add_subparsers(
        dest="action", required=True
    )
    for name in ("check", "md"):
        c = plan.add_parser(name)
        c.add_argument("plan", type=Path)
        if name == "md":
            c.add_argument("--out", "-o", type=Path)
    for command in ("story", "layout"):
        actions = sub.add_parser(
            command,
            help="message-first prose"
            if command == "story"
            else "native wireframe allocation",
        ).add_subparsers(dest="action", required=True)
        for action in (
            ("check", "md") if command == "story" else ("check", "md", "build")
        ):
            c = actions.add_parser(action)
            c.add_argument("document", type=Path)
            if action in ("md", "build"):
                c.add_argument("--out", "-o", type=Path, required=action == "build")
            if action == "build":
                c.add_argument("--theme", default="academic")
    a = sub.add_parser(
        "analyze", help="明示したディレクトリのPPTXをローカル解析・匿名化"
    )
    a.add_argument("--input", required=True, type=Path)
    a.add_argument("--out", "-o", default=Path("references/sanitized"), type=Path)
    cat = sub.add_parser("catalog").add_subparsers(dest="action", required=True)
    c = cat.add_parser("export")
    c.add_argument(
        "--out", "-o", type=Path, default=Path("design_catalog/catalog.yaml")
    )
    c = cat.add_parser("merge")
    c.add_argument(
        "--input",
        required=True,
        nargs="+",
        type=Path,
        help="匿名化JSONまたはそのディレクトリ",
    )
    c.add_argument(
        "--out", "-o", type=Path, default=Path("design_catalog/catalog.yaml")
    )
    s = sub.add_parser("skills").add_subparsers(dest="action", required=True)
    for name in ("sync", "check"):
        s.add_parser(name).add_argument("--root", type=Path, default=Path("."))
    t = sub.add_parser("tune", help="カタログ候補の採否とコメントを記録")
    t.add_argument("entry")
    t.add_argument("--catalog", type=Path, default=Path("design_catalog/catalog.yaml"))
    t.add_argument(
        "--status",
        required=True,
        choices=["accepted", "rejected", "revise", "proposed"],
    )
    t.add_argument("--comment", default="")
    sub.add_parser("themes", help="同梱テーマ一覧")
    sub.add_parser("doctor", help="レンダラ・フォントの可用性を診断")
    return p


def _write(path, text):
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


def _review_theme(pptx, explicit):
    if explicit:
        return explicit
    manifest = pptx.with_suffix(".manifest.json")
    if manifest.exists():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if data.get("theme_definition"):
            return theme_from_dict(data["theme_definition"])
        return data.get("theme", "neutral")
    return "neutral"


def _run(a):
    if a.command in ("story", "layout"):
        from .message_first import (
            build_layout,
            layout_to_markdown,
            load_layout,
            load_story,
            story_to_markdown,
            validate_layout,
            validate_story,
        )

        story = a.command == "story"
        doc = (load_story if story else load_layout)(a.document)
        issues = (validate_story if story else validate_layout)(doc)
        for issue in issues:
            print(issue)
        if any(i.level == "error" for i in issues):
            return 1
        if a.action == "md":
            _write(a.out, (story_to_markdown if story else layout_to_markdown)(doc))
        elif a.action == "build":
            print(build_layout(doc, a.out, theme=a.theme))
        else:
            count = len(doc.data.get("sections" if story else "pages", []))
            print(f"{count} {'sections' if story else 'pages'} / 0 errors")
        return 0
    if a.command == "build":
        result = build_deck(load_plan(a.plan), out=a.out, theme=a.theme, only=a.only)
        print(f"{result.n_slides} slides: {result.pptx_path}")
        for warning in result.plan_issues + result.warnings:
            print(warning)
        if a.render:
            r = render_pptx(result.pptx_path, a.out.with_suffix("") / "slides")
            print(f"{r.n} images ({r.renderer}, {r.fidelity})")
        return 0
    if a.command == "plan":
        plan = load_plan(a.plan)
        if a.action == "md":
            _write(a.out, plan_to_markdown(plan))
            return 0
        issues = validate_plan(plan)
        for issue in issues:
            print(issue)
        print(f"{len(plan.slides)} slides / {len(errors(issues))} errors")
        return int(bool(errors(issues)))
    if a.command == "render":
        result = render_pptx(
            a.pptx, a.out, renderer=a.renderer, width=a.width, slides=a.slides
        )
        print(f"{result.n} images ({result.renderer}, {result.fidelity})")
        for note in result.notes:
            print(note)
        return 0
    if a.command in ("check", "review"):
        theme = _review_theme(a.pptx, a.theme)
        if a.command == "check":
            findings = check_pptx(a.pptx, theme)
            _write(
                a.out,
                json.dumps(
                    [f.to_dict() for f in findings], ensure_ascii=False, indent=2
                ),
            )
            return int(any(f.severity == "must_fix" for f in findings))
        result = review_pptx(
            a.pptx,
            a.out or a.pptx.with_suffix(""),
            theme=theme,
            render=not a.no_render,
            renderer=a.renderer,
            sources=a.sources,
        )
        print(
            f"{len(result['findings'])} findings / visual review: {result['visual_review']}"
        )
        for note in result["notes"]:
            print(note)
        if result["visual_review"] in {"unavailable", "stale"}:
            return 2
        return int(any(f["severity"] == "must_fix" for f in result["findings"]))
    if a.command == "analyze":
        from .analysis import analyze_directory

        paths = analyze_directory(a.input, a.out)
        print(f"{len(paths)} decks analyzed locally: {a.out}")
        return 0
    if a.command == "catalog":
        from .analysis.catalog import export_catalog, merge_catalog

        if a.action == "export":
            if a.out.exists():
                raise ValueError(
                    "カタログが既に存在します。別の --out を指定してください（採否の上書きを防止）"
                )
            print(export_catalog(a.out))
        else:
            paths = []
            for path in a.input:
                paths.extend(sorted(path.glob("*.json")) if path.is_dir() else [path])
            if not paths:
                raise ValueError("匿名化JSONがありません")
            decks = [json.loads(p.read_text(encoding="utf-8")) for p in paths]
            # Accept only sanitized schemas; raw extraction must not enter the catalog.
            from .analysis.sanitize import validate_sanitized

            for deck in decks:
                validate_sanitized(deck)
            print(merge_catalog(a.out, decks))
        return 0
    if a.command == "skills":
        from .skills_sync import sync_skills

        changed = sync_skills(a.root, check=a.action == "check")
        for path in changed:
            print(path)
        print(
            f"{len(changed)} "
            + ("differences" if a.action == "check" else "files synced")
        )
        return int(a.action == "check" and bool(changed))
    if a.command == "tune":
        from .analysis.catalog import tune_catalog

        print(tune_catalog(a.catalog, a.entry, a.status, a.comment))
        return 0
    if a.command == "themes":
        for name in available_themes():
            print(f"{name}: {load_theme(name).description}")
        return 0
    if a.command == "doctor":
        fonts = None
        if shutil.which("fc-list"):
            proc = subprocess.run(
                ["fc-list", "--format=%{family}\n"],
                capture_output=True,
                check=False,
                text=True,
                timeout=20,
            )
            if proc.returncode == 0:
                fonts = {
                    name.strip().casefold()
                    for line in proc.stdout.splitlines()
                    for name in line.split(",")
                }
        data = {
            "python": sys.version.split()[0],
            "themes": available_themes(),
            "renderers": available_renderers(),
            "pdf_to_png": bool(
                importlib.util.find_spec("pymupdf") or shutil.which("pdftoppm")
            ),
            "fonts": {},
        }
        for name in available_themes():
            for font in load_theme(name).fonts.values():
                data["fonts"][font] = (
                    "unknown"
                    if fonts is None
                    else ("available" if font.casefold() in fonts else "missing")
                )
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    return 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = _parser().parse_args(argv)
    try:
        return _run(args)
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        RuntimeError,
        yaml.YAMLError,
    ) as exc:
        print(f"structured-slide-creator: {exc}", file=sys.stderr)
        return 2

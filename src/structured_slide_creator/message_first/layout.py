"""Explicit spatial allocation, story mapping and native wireframe generation."""

import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from .common import (
    Document,
    PlanIssue,
    has_errors,
    identifiers,
    mapping,
    number,
    read_document,
    records,
    required_text,
    string,
    strings,
)
from .story import load_story, validate_story


@dataclass
class LayoutDocument(Document):
    story: Document | None = None


def load_layout(path):
    base = read_document(path)
    check_layout_types(base.data)
    doc = LayoutDocument(base.data, base.path)
    if "story" in doc.data:
        doc.story = load_story(doc.resolve(doc.data["story"]))
    return doc


def check_layout_types(data):
    if "story" in data:
        string(data["story"], "story")
    page = mapping(data.get("page", {}), "page")
    for key in ("width_mm", "height_mm"):
        if key in page:
            number(page[key], "page." + key)
    typography = mapping(data.get("typography", {}), "typography")
    for key, value in typography.items():
        number(value, "typography." + key)
    for pi, page in enumerate(records(data.get("pages", []), "pages")):
        for key in ("id", "label"):
            if key in page:
                string(page[key], f"pages[{pi}].{key}")
        if "reading_order" in page:
            strings(page["reading_order"], f"pages[{pi}].reading_order")
        for ri, region in enumerate(
            records(page.get("regions", []), f"pages[{pi}].regions")
        ):
            where = f"pages[{pi}].regions[{ri}]"
            for key in ("id", "label", "kind", "purpose", "reason", "priority"):
                if key in region:
                    string(region[key], where + "." + key)
            for key in ("sections", "assets"):
                if key in region:
                    strings(region[key], where + "." + key)
            if "label_pt" in region:
                number(region["label_pt"], where + ".label_pt")
            if "box_mm" in region:
                box = region["box_mm"]
                if not isinstance(box, list) or len(box) != 4:
                    raise TypeError(
                        f"{where}.box_mm must contain four numbers [x, y, w, h]"
                    )
                for i, value in enumerate(box):
                    number(value, f"{where}.box_mm[{i}]")


def ordered_regions(page):
    by_id = {r.get("id"): r for r in page.get("regions", [])}
    order = page.get("reading_order", [])
    return [by_id[r] for r in order if r in by_id] + [
        r for r in page.get("regions", []) if r.get("id") not in order
    ]


def label_text(region):
    label = region.get("label", "")
    detail = ", ".join(region.get("assets", [])) or region.get("kind", "")
    return label + ("\n" + detail if detail and detail != label else "")


def label_size(doc, region, theme=None):
    sizes = doc.data.get("typography", {})
    default = (
        sizes.get("title_pt", 28)
        if region.get("kind") == "title"
        else sizes.get("label_pt", 16)
    )
    return region.get("label_pt", default)


def validate_layout(doc):
    from ..textmetrics import wrapped_line_count

    check_layout_types(doc.data)
    data = doc.data
    issues = []
    page = data.get("page", {})
    for key in ("width_mm", "height_mm"):
        if key not in page:
            issues.append(PlanIssue("error", "page", f"{key} is required"))
        elif not 25.4 <= page[key] <= 1422.4:
            issues.append(
                PlanIssue(
                    "error",
                    "page." + key,
                    "PowerPoint page dimensions must be between 25.4 and 1422.4 mm",
                )
            )
    for key, value in data.get("typography", {}).items():
        if value <= 0:
            issues.append(
                PlanIssue("error", "typography." + key, "font size must be positive")
            )
    pages = data.get("pages", [])
    if not pages:
        issues.append(PlanIssue("error", "pages", "at least one page is required"))
    identifiers(pages, "pages", issues)
    section_map = {
        s["id"]: s
        for s in (doc.story.data.get("sections", []) if doc.story else [])
        if "id" in s
    }
    asset_ids = {
        s["id"]
        for s in (doc.story.data.get("assets", []) if doc.story else [])
        if "id" in s
    }
    if doc.story:
        issues.extend(
            PlanIssue(i.level, "story." + i.where, i.message)
            for i in validate_story(doc.story)
        )
    occurrence = []
    for pi, p in enumerate(pages):
        where = f"pages[{pi}] ({p.get('id', '')})"
        regions = p.get("regions", [])
        ids = identifiers(regions, where + ".regions", issues)
        if not regions:
            issues.append(PlanIssue("warning", where, "page has no regions"))
        order = p.get("reading_order", [])
        if len(order) != len(set(order)):
            issues.append(PlanIssue("error", where, "duplicate reading_order region"))
        for rid in order:
            if rid not in ids:
                issues.append(
                    PlanIssue("error", where, f"unknown reading_order region {rid!r}")
                )
        if order and set(order) != ids:
            issues.append(
                PlanIssue(
                    "warning",
                    where,
                    "regions missing from reading_order are appended in file order",
                )
            )
        boxes = []
        for ri, r in enumerate(regions):
            rw = where + f".regions[{ri}] ({r.get('id', '')})"
            required_text(r, ["label", "kind"], rw, issues)
            if r.get("priority", "supporting") not in {
                "primary",
                "supporting",
                "context",
            }:
                issues.append(
                    PlanIssue(
                        "error", rw, "priority must be primary, supporting or context"
                    )
                )
            for key, known in [("sections", section_map), ("assets", asset_ids)]:
                if len(r.get(key, [])) != len(set(r.get(key, []))):
                    issues.append(PlanIssue("error", rw, f"duplicate {key} reference"))
                if doc.story:
                    for ref in r.get(key, []):
                        if ref not in known:
                            issues.append(
                                PlanIssue(
                                    "error", rw, f"unknown {key} reference {ref!r}"
                                )
                            )
                elif r.get(key):
                    issues.append(
                        PlanIssue(
                            "warning",
                            rw,
                            f"{key} references cannot be verified without a linked story",
                        )
                    )
            if "box_mm" not in r:
                issues.append(PlanIssue("error", rw, "box_mm is required"))
                continue
            x, y, w, h = r["box_mm"]
            if w <= 0 or h <= 0:
                issues.append(
                    PlanIssue("error", rw, "region width/height must be positive")
                )
                continue
            if (
                x < 0
                or y < 0
                or x + w > page.get("width_mm", 0) + 1e-7
                or y + h > page.get("height_mm", 0) + 1e-7
            ):
                issues.append(PlanIssue("error", rw, "region lies outside the page"))
            boxes.append((r.get("id"), (x, y, w, h)))
            size = label_size(doc, r)
            if size <= 0:
                issues.append(PlanIssue("error", rw, "label_pt must be positive"))
                continue
            # Matches the builder's explicit leading and padding; never silently shrink.
            needed_mm = (
                wrapped_line_count(label_text(r), size, max(0.001, (w - 4) / 25.4))
                * size
                / 72
                * 25.4
                * 1.15
            )
            if w <= 4 or h <= 4 or needed_mm > h - 4 + 0.05:
                issues.append(
                    PlanIssue(
                        "error",
                        rw,
                        f"wireframe label does not fit at {size:g} pt; shorten it or enlarge the region",
                    )
                )
        for i, (aid, a) in enumerate(boxes):
            for bid, b in boxes[i + 1 :]:
                ax, ay, aw, ah = a
                bx, by, bw, bh = b
                overlap = (
                    min(ax + aw, bx + bw) - max(ax, bx) > 1e-7
                    and min(ay + ah, by + bh) - max(ay, by) > 1e-7
                )
                contains = (
                    ax <= bx and ay <= by and ax + aw >= bx + bw and ay + ah >= by + bh
                ) or (
                    bx <= ax and by <= ay and bx + bw >= ax + aw and by + bh >= ay + ah
                )
                if overlap and not contains:
                    issues.append(
                        PlanIssue(
                            "warning",
                            where,
                            f"overlap between {aid!r} and {bid!r}; inspect intended placement",
                        )
                    )
        for r in ordered_regions(p):
            for sid in r.get("sections", []):
                if sid not in occurrence:
                    occurrence.append(sid)
    if doc.story:
        positions = {sid: i for i, sid in enumerate(occurrence)}
        introducers = {
            c: s["id"] for s in section_map.values() for c in s.get("introduces", [])
        }
        for sid, section in section_map.items():
            if sid not in positions:
                issues.append(
                    PlanIssue("warning", "story mapping", f"unmapped section {sid!r}")
                )
                continue
            requirements = list(section.get("depends_on", [])) + [
                introducers[c] for c in section.get("uses", []) if c in introducers
            ]
            for earlier in dict.fromkeys(requirements):
                if earlier not in positions:
                    issues.append(
                        PlanIssue(
                            "warning",
                            sid,
                            f"required context section {earlier!r} is unmapped",
                        )
                    )
                elif positions[earlier] >= positions[sid]:
                    issues.append(
                        PlanIssue(
                            "error",
                            sid,
                            f"layout reading order requires {earlier!r} before {sid!r}",
                        )
                    )
    return issues


def layout_to_markdown(doc):
    lines = ["# Layout allocation", "", f"Page: {doc.data.get('page', {})}", ""]
    if doc.story:
        lines += ["**Central message:** " + doc.story.data.get("message", ""), ""]
    sections = {
        s["id"]: s
        for s in (doc.story.data.get("sections", []) if doc.story else [])
        if "id" in s
    }
    assets = {
        a["id"]: a
        for a in (doc.story.data.get("assets", []) if doc.story else [])
        if "id" in a
    }
    for page in doc.data.get("pages", []):
        lines += [f"## {page.get('id', '')} — {page.get('label', '')}", ""]
        for i, r in enumerate(ordered_regions(page), 1):
            b = r.get("box_mm", [])
            area = b[2] * b[3] if len(b) == 4 else 0
            lines += [
                f"### {i}. {r.get('id', '')} — {r.get('label', '')}",
                "",
                f"- Role: {r.get('kind', '')} / {r.get('priority', 'supporting')}",
                f"- Geometry (mm): {b}; area={area:g} mm²; label={label_size(doc, r):g} pt",
                f"- Purpose: {r.get('purpose') or r.get('reason') or '(not specified)'}",
            ]
            for sid in r.get("sections", []):
                lines += [
                    f"- Claim [{sid}]: {sections.get(sid, {}).get('claim', '(unlinked)')}"
                ]
            for aid in r.get("assets", []):
                a = assets.get(aid, {})
                detail = " / ".join(
                    str(a.get(k, "")) for k in ["role", "source", "path"] if a.get(k)
                )
                lines += [f"- Reserved asset [{aid}]: {detail or '(unlinked)'}"]
            lines.append("")
    return "\n".join(lines)


def build_layout(doc, out, *, theme="academic"):
    from pptx.util import Pt

    from ..design.tokens import load_theme
    from ..generation import shapes as S
    from ..generation.deck import Deck
    from ..units import Box

    issues = validate_layout(doc)
    if has_errors(issues):
        raise ValueError("\n".join(str(i) for i in issues if i.level == "error"))
    style = deepcopy(load_theme(theme))
    page = doc.data["page"]
    style.raw["slide"] = {
        "width_in": page["width_mm"] / 25.4,
        "height_in": page["height_mm"] / 25.4,
    }
    sizes = [
        label_size(doc, r) for p in doc.data["pages"] for r in p.get("regions", [])
    ]
    if sizes:
        style.limits["min_font_pt"] = min(
            style.limits.get("min_font_pt", 0), min(sizes)
        )
    deck = Deck(style)
    for page_spec in doc.data["pages"]:
        ctx = deck.add_slide(slide_id=page_spec["id"])
        ctx.show_footer = False
        for r in page_spec.get("regions", []):
            x, y, w, h = r["box_mm"]
            b = Box(x / 25.4, y / 25.4, w / 25.4, h / 25.4)
            fill = "accent_pale" if r.get("priority") == "primary" else "surface"
            S.add_rect(
                ctx.slide, style, b, fill=fill, line="rule", name=f"region-{r['id']}"
            )
            tb = S.new_textbox(
                ctx.slide,
                Box((x + 2) / 25.4, (y + 2) / 25.4, (w - 4) / 25.4, (h - 4) / 25.4),
                name=f"label-{r['id']}",
            )
            tb.text_frame.margin_left = tb.text_frame.margin_right = (
                tb.text_frame.margin_top
            ) = tb.text_frame.margin_bottom = 0
            size = label_size(doc, r)
            st = style.style("diagram_label").with_(size=size, color="ink", bold=True)
            for i, line in enumerate(label_text(r).split("\n")):
                p = S.write_paragraph(
                    tb.text_frame, style, line, st, first=i == 0, space_after_pt=0
                )
                # write_paragraph returns Paragraph; exact leading avoids font-specific expansion.
                p.line_spacing = Pt(size * 1.15)
    out = Path(out)
    deck.save(out)
    manifest = {
        "artifact": "native_wireframe_only",
        "layout": str(doc.path) if doc.path else None,
        "story": str(doc.story.path) if doc.story else None,
        "pages": len(doc.data["pages"]),
        "theme": style.name,
        "theme_definition": style.raw,
        "issues": [
            {"level": i.level, "where": i.where, "message": i.message} for i in issues
        ],
    }
    out.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return out

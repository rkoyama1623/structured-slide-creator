"""Geometry-based checks; text fitting and overlap findings are estimates."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.enum.dml import MSO_FILL_TYPE

from ..design.contrast import contrast_ratio, required_ratio
from ..design.rules import DesignRuleError, check_font_size
from ..design.tokens import Theme, load_theme
from ..textmetrics import visual_length, wrapped_line_count
from ..units import Box, EMU_PER_INCH


@dataclass
class Finding:
    severity: str
    slide: int
    shape: str
    kind: str
    message: str
    box: Box | None = None

    def to_dict(self):
        return asdict(self)


def shape_box(shape) -> Box:
    return Box(
        *(
            float(v) / EMU_PER_INCH
            for v in (shape.left, shape.top, shape.width, shape.height)
        )
    )


def walk_shapes(shapes):
    for shape in shapes:
        yield shape
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            yield from walk_shapes(shape.shapes)


def solid_color(fill):
    try:
        if fill.type == MSO_FILL_TYPE.SOLID and fill.fore_color.rgb is not None:
            return "#" + str(fill.fore_color.rgb)
    except (AttributeError, TypeError):
        pass
    return None


def _role(name, table=False):
    if table:
        return "table_body"
    if name.startswith("footer"):
        return "footer"
    if name.endswith("-text") and name[:-5] in (
        "note",
        "caption",
        "diagram_note",
        "chart_text",
    ):
        return name[:-5]
    return {
        "body-text": "body",
        "bullets": "bullet_1",
        "lead": "lead",
        "lead-text": "lead",
        "heading": "heading",
        "slide-title": "slide_title",
        "deck-title": "deck_title",
    }.get(name, "text")


def _text_checks(tf, box, theme, slide_no, name, bg, *, table=False):
    findings = []
    role = _role(name, table)
    default = theme.type_styles.get(role, theme.style("body"))
    width = max(0.01, box.w - (tf.margin_left + tf.margin_right) / EMU_PER_INCH)
    height = 0.0
    for p in tf.paragraphs:
        if not p.text:
            continue
        sizes = []
        for run in p.runs:
            if not run.text.strip():
                continue
            pt = run.font.size or p.font.size
            pt = pt.pt if pt is not None else default.size
            sizes.append(pt)
            try:
                check_font_size(theme, pt, role=role)
            except DesignRuleError:
                findings.append(
                    Finding(
                        "must_fix",
                        slide_no,
                        name,
                        "font_size",
                        f"{pt:g}pt: テーマのフォント下限未満です",
                        box,
                    )
                )
            try:
                color = run.font.color.rgb
            except (AttributeError, TypeError):
                color = None
            if color is not None and bg:
                ratio = contrast_ratio("#" + str(color), bg)
                if ratio < required_ratio(pt, bool(run.font.bold)):
                    findings.append(
                        Finding(
                            "should_fix",
                            slide_no,
                            name,
                            "contrast",
                            f"文字と背景のコントラスト比 {ratio:.2f}",
                            box,
                        )
                    )
        size = max(sizes, default=default.size)
        spacing = p.line_spacing
        line_h = (
            spacing.pt / 72 if hasattr(spacing, "pt") else size / 72 * (spacing or 1.22)
        )
        indent = p._p.get_or_add_pPr().get("marL", "0")
        n = wrapped_line_count(
            p.text, size, max(0.01, width - int(indent) / EMU_PER_INCH)
        )
        height += (
            n * line_h
            + (p.space_before or 0) / EMU_PER_INCH
            + (p.space_after or 0) / EMU_PER_INCH
        )
    available = box.h - (tf.margin_top + tf.margin_bottom) / EMU_PER_INCH
    if height > available * 1.12 + 0.02:
        findings.append(
            Finding(
                "should_fix",
                slide_no,
                name,
                "table_overflow" if table else "text_overflow",
                f"文字の概算高さ {height:.2f}in > 枠 {available:.2f}in。実描画を確認してください",
                box,
            )
        )
    # One finding per shape and category keeps reports readable.
    return list({f.kind: f for f in findings}.values())


def check_pptx(path, theme: Theme | str = "neutral", *, manifest=None) -> list[Finding]:
    theme = theme if isinstance(theme, Theme) else load_theme(theme)
    prs = Presentation(str(path))
    sw, sh = prs.slide_width / EMU_PER_INCH, prs.slide_height / EMU_PER_INCH
    findings, titles = [], []
    if manifest is None:
        import json

        candidate = Path(path).with_suffix(".manifest.json")
        manifest = (
            json.loads(candidate.read_text(encoding="utf-8"))
            if candidate.exists()
            else {}
        )
    title_exclusions = {
        s["index"]
        for s in manifest.get("slides", [])
        if s.get("layout") in ("closing", "title_cover", "section_divider")
    }
    for index, slide in enumerate(prs.slides, 1):
        shapes = list(walk_shapes(slide.shapes))
        chars = 0.0
        foreground = []
        for z, shape in enumerate(shapes):
            box = shape_box(shape)
            name = shape.name

            def add(severity, kind, msg):
                findings.append(Finding(severity, index, name, kind, msg, box))

            if (
                box.x < -0.01
                or box.y < -0.01
                or box.right > sw + 0.01
                or box.bottom > sh + 0.01
            ):
                add("must_fix", "outside_slide", "図形がスライド範囲をはみ出しています")
            if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
                continue
            bg = solid_color(slide.background.fill) or theme.color("bg")
            for below in reversed(shapes[: z + 1]):
                if (
                    hasattr(below, "fill")
                    and shape_box(below).intersection_area(box) >= box.area * 0.98
                ):
                    color = solid_color(below.fill)
                    if color:
                        bg = color
                        break
            if shape.has_text_frame:
                chars += visual_length(shape.text)
                findings.extend(
                    _text_checks(shape.text_frame, box, theme, index, name, bg)
                )
                if name == "slide-title" and index not in title_exclusions:
                    size = next(
                        (
                            r.font.size.pt
                            for p in shape.text_frame.paragraphs
                            for r in p.runs
                            if r.font.size
                        ),
                        None,
                    )
                    titles.append((index, name, box, size))
            if shape.has_table:
                table = shape.table
                y = box.y
                for ri, row in enumerate(table.rows):
                    x = box.x
                    for ci, col in enumerate(table.columns):
                        cell = table.cell(ri, ci)
                        cb = Box(
                            x, y, col.width / EMU_PER_INCH, row.height / EMU_PER_INCH
                        )
                        if not cell.is_spanned:
                            if cell.is_merge_origin:
                                cb = Box(
                                    x,
                                    y,
                                    sum(
                                        table.columns[c].width
                                        for c in range(ci, ci + cell.span_width)
                                    )
                                    / EMU_PER_INCH,
                                    sum(
                                        table.rows[r].height
                                        for r in range(ri, ri + cell.span_height)
                                    )
                                    / EMU_PER_INCH,
                                )
                            chars += visual_length(cell.text)
                            findings.extend(
                                _text_checks(
                                    cell.text_frame,
                                    cb,
                                    theme,
                                    index,
                                    f"{name}[{ri + 1},{ci + 1}]",
                                    solid_color(cell.fill) or bg,
                                    table=True,
                                )
                            )
                        x += (
                            cb.w
                            if not cell.is_merge_origin
                            else col.width / EMU_PER_INCH
                        )
                    y += row.height / EMU_PER_INCH
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                iw, ih = shape.image.size
                cw = 1 - shape.crop_left - shape.crop_right
                ch = 1 - shape.crop_top - shape.crop_bottom
                if box.h and ih and cw > 0 and ch > 0:
                    expected = iw * cw / (ih * ch)
                    if abs(box.w / box.h / expected - 1) > 0.03:
                        add(
                            "should_fix",
                            "image_aspect",
                            "画像の縦横比が元画像から3%以上変化しています",
                        )
            text = shape.has_text_frame and bool(shape.text.strip())
            if box.area > 0.001 and (
                text
                or shape.has_table
                or shape.has_chart
                or shape.shape_type == MSO_SHAPE_TYPE.PICTURE
            ):
                if not name.startswith(("note-", "edge-label", "footer")):
                    foreground.append((name, box))
        for ai, (an, a) in enumerate(foreground):
            for bn, b in foreground[ai + 1 :]:
                area = a.intersection_area(b)
                if area > min(a.area, b.area) * 0.05:
                    findings.append(
                        Finding(
                            "should_fix",
                            index,
                            an,
                            "overlap",
                            f"{bn} と5%以上重なっています（意図した配置か確認）",
                            a,
                        )
                    )
        # Near alignment clusters indicate a likely accidental offset; arbitrary layouts need no fixed grid.
        for axis in ("x", "y"):
            ordered = sorted(
                ((getattr(b, axis), n, b) for n, b in foreground),
                key=lambda item: item[0],
            )
            for (v1, n1, b1), (v2, n2, b2) in zip(ordered, ordered[1:]):
                if 0.02 < v2 - v1 <= 0.08:
                    findings.append(
                        Finding(
                            "nice_to_fix",
                            index,
                            n2,
                            "alignment",
                            f"{n1} との{axis}端の差が {v2 - v1:.3f}in です",
                            b2,
                        )
                    )
        cap = theme.limits.get("max_chars_per_slide", 460)
        if chars > cap:
            findings.append(
                Finding(
                    "should_fix",
                    index,
                    "",
                    "text_density",
                    f"換算文字数 {chars:.0f} が上限 {cap} を超えています",
                )
            )
    if len(titles) > 1:
        from statistics import median

        mx, my = median(t[2].x for t in titles), median(t[2].y for t in titles)
        sizes = [t[3] for t in titles if t[3] is not None]
        ms = median(sizes) if sizes else None
        for i, name, box, size in titles:
            if (
                abs(box.x - mx) > 0.02
                or abs(box.y - my) > 0.02
                or (ms and size and abs(size - ms) > 0.5)
            ):
                findings.append(
                    Finding(
                        "should_fix",
                        i,
                        name,
                        "title_consistency",
                        "通常ページのタイトル位置またはサイズが他ページと異なります",
                        box,
                    )
                )
    return findings

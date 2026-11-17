"""ネイティブチャート。PowerPoint 上でデータ編集できる形で作る。

数値は呼び出し側が与えたものだけを描く。欠損は補間せず、明示的に欠損として扱う
（実験結果の捏造を防ぐため、空の系列や非数値はエラーにする）。
"""

from __future__ import annotations

from typing import Any, Sequence

from pptx.chart.data import CategoryChartData, XyChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_LEGEND_POSITION
from pptx.oxml.ns import qn
from pptx.util import Pt

from ..design.rules import DesignRuleError, check_font_size
from ..units import Box, inches_to_emu
from .components import add_caption
from .deck import SlideCtx

CHART_KINDS = {
    "bar": "COLUMN_CLUSTERED",
    "column": "COLUMN_CLUSTERED",
    "bar_stacked": "COLUMN_STACKED",
    "hbar": "BAR_CLUSTERED",
    "hbar_stacked": "BAR_STACKED",
    "line": "LINE",
    "line_markers": "LINE_MARKERS",
    "area": "AREA",
    "scatter": "XY_SCATTER",
    "scatter_lines": "XY_SCATTER_LINES",
    "pie": "PIE",
}


def _xl(kind: str):
    from pptx.enum.chart import XL_CHART_TYPE

    name = CHART_KINDS.get(kind)
    if name is None:
        raise DesignRuleError(
            f"unknown chart kind {kind!r}. available: {sorted(CHART_KINDS)}"
        )
    return getattr(XL_CHART_TYPE, name)


def _validate_values(values: Sequence[Any], series_name: str) -> list[float | None]:
    out: list[float | None] = []
    for v in values:
        if v is None or (isinstance(v, str) and v.strip() in ("", "-", "—", "NA", "N/A")):
            out.append(None)      # 欠損はプロットしない（捏造しない）
            continue
        try:
            out.append(float(v))
        except (TypeError, ValueError) as exc:
            raise DesignRuleError(
                f"chart series {series_name!r} に数値でない値 {v!r} が含まれます。"
                f" 実測値を入れてください（推定値を使う場合はキャプションに明記）。"
            ) from exc
    if all(v is None for v in out):
        raise DesignRuleError(f"chart series {series_name!r} の値が空です。")
    return out


def add_chart(
    ctx: SlideCtx,
    box: Box,
    kind: str,
    categories: Sequence[Any],
    series: Sequence[dict] | dict,
    *,
    caption: str = "",
    y_title: str = "",
    x_title: str = "",
    number_format: str | None = None,
    legend: bool | None = None,
    gridlines: bool = True,
    y_min: float | None = None,
    y_max: float | None = None,
    numbered: bool | None = None,
) -> Box:
    """ネイティブチャートを描く。

    series: [{"name": "提案手法", "values": [...], "color": "accent"(省略可)}, ...]
            散布図の場合は {"name":…, "points": [(x, y), ...]}
    """
    theme = ctx.theme
    if isinstance(series, dict):
        series = [series]
    series = [dict(s) for s in series]
    if not series:
        raise DesignRuleError("add_chart: 系列が空です。データを与えてください。")

    conv = theme.conventions
    if numbered is None:
        numbered = bool(conv.get("numbered_figures", False))
    cap_text = caption
    if caption and numbered:
        cap_text = f"{conv.get('figure_caption_prefix', '図')}{ctx.next_figure_number()} {caption}"
    cap_style = theme.style("caption")
    cap_h = (cap_style.size / 72.0 * 1.9) if cap_text else 0.0
    chart_box = Box(box.x, box.y, box.w, max(box.h - cap_h, 0.6))

    is_xy = kind.startswith("scatter")
    if is_xy:
        data = XyChartData()
        for s in series:
            pts = s.get("points") or []
            if not pts:
                raise DesignRuleError(f"scatter series {s.get('name')!r} に points がありません。")
            sd = data.add_series(str(s.get("name", "")))
            for x, y in pts:
                sd.add_data_point(float(x), float(y))
    else:
        data = CategoryChartData()
        data.categories = [str(c) for c in categories]
        for s in series:
            values = _validate_values(s.get("values") or [], str(s.get("name", "")))
            if len(values) != len(categories):
                raise DesignRuleError(
                    f"series {s.get('name')!r}: 値の数 {len(values)} が "
                    f"カテゴリ数 {len(categories)} と一致しません。"
                )
            data.add_series(str(s.get("name", "")), values, number_format)

    gf = ctx.slide.shapes.add_chart(
        _xl(kind),
        inches_to_emu(chart_box.x),
        inches_to_emu(chart_box.y),
        inches_to_emu(chart_box.w),
        inches_to_emu(chart_box.h),
        data,
    )
    gf.name = f"chart-{ctx.slide_id}"
    chart = gf.chart
    _style_chart(ctx, chart, series, kind, legend=legend, gridlines=gridlines,
                 y_title=y_title, x_title=x_title, y_min=y_min, y_max=y_max)

    if cap_text:
        add_caption(ctx, Box(box.x, chart_box.bottom + 0.04, box.w, cap_h), cap_text,
                    align="center")
    return box


def _style_chart(
    ctx: SlideCtx,
    chart,
    series: Sequence[dict],
    kind: str,
    *,
    legend: bool | None,
    gridlines: bool,
    y_title: str,
    x_title: str,
    y_min: float | None,
    y_max: float | None,
) -> None:
    theme = ctx.theme
    text_style = theme.style("chart_text")
    pt = check_font_size(theme, text_style.size, role="chart_text")

    chart.font.size = Pt(pt)
    chart.font.name = theme.font("ja")
    chart.font.color.rgb = RGBColor(*theme.rgb(text_style.color))
    chart.has_title = False

    # 外枠と背景（枠線なし・白背景）
    _set_chart_space_plain(chart, theme)

    show_legend = (len(series) > 1) if legend is None else legend
    chart.has_legend = show_legend
    if show_legend:
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM
        chart.legend.include_in_layout = False
        chart.legend.font.size = Pt(pt)

    # 系列色
    for i, s in enumerate(chart.series):
        color = series[i].get("color") if i < len(series) else None
        hexc = theme.color(color) if color else theme.series_color(i)
        rgb = RGBColor(*theme.rgb(hexc))
        if kind.startswith(("line", "scatter")):
            s.format.line.color.rgb = rgb
            s.format.line.width = Pt(2.0)
            try:
                s.marker.format.fill.solid()
                s.marker.format.fill.fore_color.rgb = rgb
                s.marker.format.line.color.rgb = rgb
            except Exception:  # noqa: BLE001 - マーカ非対応のチャート種別
                pass
        else:
            s.format.fill.solid()
            s.format.fill.fore_color.rgb = rgb
            s.format.line.fill.background()

    if kind == "pie":
        return

    try:
        va = chart.value_axis
        va.has_major_gridlines = gridlines
        if gridlines:
            va.major_gridlines.format.line.color.rgb = RGBColor(*theme.rgb("rule_soft"))
            va.major_gridlines.format.line.width = Pt(0.75)
        va.format.line.color.rgb = RGBColor(*theme.rgb("rule"))
        va.tick_labels.font.size = Pt(pt)
        if y_min is not None:
            va.minimum_scale = y_min
        if y_max is not None:
            va.maximum_scale = y_max
        if y_title:
            va.has_title = True
            va.axis_title.text_frame.text = y_title
            va.axis_title.text_frame.paragraphs[0].runs[0].font.size = Pt(pt)

        ca = chart.category_axis if not kind.startswith("scatter") else chart.category_axis
        ca.has_major_gridlines = False
        ca.format.line.color.rgb = RGBColor(*theme.rgb("rule"))
        ca.tick_labels.font.size = Pt(pt)
        ca.tick_labels.offset = 100 if hasattr(ca.tick_labels, "offset") else None
        if x_title:
            ca.has_title = True
            ca.axis_title.text_frame.text = x_title
            ca.axis_title.text_frame.paragraphs[0].runs[0].font.size = Pt(pt)
    except Exception:  # noqa: BLE001 - 軸を持たないチャート種別
        pass

    # 棒の間隔（詰めすぎ・空きすぎを避ける）
    try:
        plot = chart.plots[0]
        plot.gap_width = 60
        plot.overlap = -10 if "stacked" not in kind else 100
        plot.vary_by_categories = False
    except Exception:  # noqa: BLE001
        pass


def _set_chart_space_plain(chart, theme) -> None:
    cs = chart._chartSpace
    for tag in ("c:spPr",):
        existing = cs.find(qn(tag))
        if existing is not None:
            cs.remove(existing)
    spPr = cs.makeelement(qn("c:spPr"), {})
    fill = spPr.makeelement(qn("a:noFill"), {})
    ln = spPr.makeelement(qn("a:ln"), {})
    ln.append(ln.makeelement(qn("a:noFill"), {}))
    spPr.append(fill)
    spPr.append(ln)
    # c:spPr は c:txPr の直前に置く必要がある
    txpr = cs.find(qn("c:txPr"))
    if txpr is not None:
        txpr.addprevious(spPr)
    else:
        cs.append(spPr)

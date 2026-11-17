"""デザイントークン（テーマ）の読み込みと解決。

テーマは styles/*.yaml に置く。`extends:` で親テーマを継承し、
配色・文字サイズ・余白・一部のレイアウト規則だけを差し替える。
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .contrast import hex_to_rgb

DEFAULT_THEME = "neutral"
_ASPECTS = {"16:9": (13.333, 7.5), "4:3": (10.0, 7.5)}


def styles_dir() -> Path:
    """リポジトリ同梱の styles/ を返す（環境変数 STRUCTURED_SLIDE_CREATOR_STYLES で上書き可）。"""
    import os

    env = os.environ.get("STRUCTURED_SLIDE_CREATOR_STYLES")
    if env:
        return Path(env)
    from ..resources import asset_root

    return asset_root() / "styles"


def project_root() -> Path:
    """src/structured_slide_creator/design/tokens.py -> リポジトリルート。"""
    return Path(__file__).resolve().parents[3]


def available_themes() -> list[str]:
    d = styles_dir()
    return sorted(p.stem for p in d.glob("*.yaml")) if d.exists() else []


def _deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


@dataclass(frozen=True)
class TextStyle:
    """1 つの文字スタイル。色はテーマのカラーキー名、または #RRGGBB。"""

    size: float
    bold: bool = False
    italic: bool = False
    color: str = "ink"
    font: str = "ja"          # fonts の論理名（ja / latin / mono / math）
    role: str = "text"

    def scaled(self, factor: float) -> "TextStyle":
        return TextStyle(
            size=round(self.size * factor, 1),
            bold=self.bold,
            italic=self.italic,
            color=self.color,
            font=self.font,
            role=self.role,
        )

    def with_(self, **kw: Any) -> "TextStyle":
        data = dict(size=self.size, bold=self.bold, italic=self.italic,
                    color=self.color, font=self.font, role=self.role)
        data.update(kw)
        return TextStyle(**data)


@dataclass
class Theme:
    name: str
    description: str
    raw: dict
    fonts: dict
    colors: dict
    type_styles: dict[str, TextStyle]
    layout: dict
    footer: dict
    limits: dict
    conventions: dict = field(default_factory=dict)
    source_path: Path | None = None

    # --- 基本情報 --------------------------------------------------------
    @property
    def slide_size_in(self) -> tuple[float, float]:
        s = self.raw.get("slide", {})
        aspect = s.get("aspect", "16:9")
        w, h = _ASPECTS.get(aspect, (s.get("width_in", 13.333), s.get("height_in", 7.5)))
        return float(s.get("width_in", w)), float(s.get("height_in", h))

    # --- 解決ヘルパ ------------------------------------------------------
    def color(self, key: str) -> str:
        """カラーキー or #RRGGBB を #RRGGBB に解決する。"""
        if not key:
            return self.colors["ink"]
        if key.startswith("#"):
            return key.upper()
        if key in self.colors and isinstance(self.colors[key], str):
            return str(self.colors[key]).upper()
        raise KeyError(f"unknown color token {key!r} in theme {self.name}")

    def rgb(self, key: str) -> tuple[int, int, int]:
        return hex_to_rgb(self.color(key))

    def series_color(self, index: int) -> str:
        series = self.colors.get("series") or [self.colors["accent"]]
        return str(series[index % len(series)]).upper()

    def font(self, logical: str) -> str:
        return self.fonts.get(logical, self.fonts.get("ja", "Yu Gothic UI"))

    def style(self, name: str) -> TextStyle:
        if name not in self.type_styles:
            raise KeyError(
                f"unknown text style {name!r} in theme {self.name}. "
                f"available: {sorted(self.type_styles)}"
            )
        return self.type_styles[name]

    def lay(self, key: str, default: Any = None) -> Any:
        return self.layout.get(key, default)

    # --- 代表的な領域 ----------------------------------------------------
    def content_box(self, *, has_lead: bool = True):
        from ..units import Box

        w, h = self.slide_size_in
        mx = float(self.lay("margin_x_in", 0.62))
        top = float(self.lay("content_top_in" if has_lead else "content_top_no_lead_in", 1.6))
        bottom = float(self.lay("content_bottom_in", h - 0.62))
        return Box(mx, top, w - 2 * mx, bottom - top)

    def full_box(self):
        from ..units import Box

        w, h = self.slide_size_in
        mx = float(self.lay("margin_x_in", 0.62))
        mt = float(self.lay("margin_top_in", 0.46))
        mb = float(self.lay("margin_bottom_in", 0.40))
        return Box(mx, mt, w - 2 * mx, h - mt - mb)


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _resolve_raw(name_or_path: str, _seen: tuple[Path, ...] = ()) -> tuple[dict, Path]:
    path = Path(name_or_path).expanduser()
    if not path.suffix:
        path = styles_dir() / f"{name_or_path}.yaml"
    path = path.resolve()
    if path in _seen:
        raise ValueError(f"circular theme inheritance: {_seen + (path,)}")
    if not path.exists():
        raise FileNotFoundError(f"theme {name_or_path!r} not found: {path}")
    data = _load_yaml(path)
    if not isinstance(data, dict):
        raise ValueError(f"theme must be a mapping: {path}")
    parent = data.get("extends")
    if parent:
        relative = path.parent / str(parent)
        if not relative.suffix:
            relative = relative.with_suffix('.yaml')
        base, _ = _resolve_raw(str(relative) if relative.exists() else str(parent), _seen + (path,))
        data = _deep_merge(base, data)
        data.pop("extends", None)
    return data, path


def load_theme(name_or_path: str = DEFAULT_THEME) -> Theme:
    raw, path = _resolve_raw(name_or_path)
    return theme_from_dict(raw, source_path=path)


def theme_from_dict(raw: dict, *, source_path: Path | None = None) -> Theme:
    """Restore a resolved theme definition saved in a build manifest."""
    raw = copy.deepcopy(raw)
    path = source_path or Path(str(raw.get("name", "custom")))
    styles: dict[str, TextStyle] = {}
    for key, spec in (raw.get("type") or {}).items():
        spec = dict(spec or {})
        styles[key] = TextStyle(
            size=float(spec.get("size", 13.5)),
            bold=bool(spec.get("bold", False)),
            italic=bool(spec.get("italic", False)),
            color=str(spec.get("color", "ink")),
            font=str(spec.get("font", "ja")),
            role=key,
        )
    return Theme(
        name=str(raw.get("name", Path(path).stem)),
        description=str(raw.get("description", "")),
        raw=raw,
        fonts=dict(raw.get("fonts") or {}),
        colors=dict(raw.get("colors") or {}),
        type_styles=styles,
        layout=dict(raw.get("layout") or {}),
        footer=dict(raw.get("footer") or {}),
        limits=dict(raw.get("limits") or {}),
        conventions=dict(raw.get("conventions") or {}),
        source_path=source_path,
    )

"""寸法と矩形。内部計算は常に inch で行い、python-pptx へ渡す直前に EMU 化する。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

EMU_PER_INCH = 914400
EMU_PER_POINT = 12700


def inches_to_emu(value: float) -> int:
    return int(round(value * EMU_PER_INCH))


def pt_to_inches(value: float) -> float:
    return value / 72.0


def inches_to_pt(value: float) -> float:
    return value * 72.0


@dataclass(frozen=True)
class Box:
    """スライド上の矩形領域（inch）。レイアウト計算の唯一の通貨。"""

    x: float
    y: float
    w: float
    h: float

    # --- 派生プロパティ ------------------------------------------------
    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    @property
    def emu(self) -> tuple[int, int, int, int]:
        return (
            inches_to_emu(self.x),
            inches_to_emu(self.y),
            inches_to_emu(self.w),
            inches_to_emu(self.h),
        )

    # --- 変形 ----------------------------------------------------------
    def inset(self, dx: float = 0.0, dy: float | None = None) -> "Box":
        dy = dx if dy is None else dy
        return Box(self.x + dx, self.y + dy, self.w - 2 * dx, self.h - 2 * dy)

    def offset(self, dx: float = 0.0, dy: float = 0.0) -> "Box":
        return replace(self, x=self.x + dx, y=self.y + dy)

    def with_h(self, h: float) -> "Box":
        return replace(self, h=h)

    def with_w(self, w: float) -> "Box":
        return replace(self, w=w)

    def take_top(self, h: float, gap: float = 0.0) -> tuple["Box", "Box"]:
        """上から h を切り出し、(切り出した領域, 残り) を返す。"""
        top = Box(self.x, self.y, self.w, h)
        rest = Box(self.x, self.y + h + gap, self.w, max(0.0, self.h - h - gap))
        return top, rest

    def take_bottom(self, h: float, gap: float = 0.0) -> tuple["Box", "Box"]:
        bottom = Box(self.x, self.bottom - h, self.w, h)
        rest = Box(self.x, self.y, self.w, max(0.0, self.h - h - gap))
        return bottom, rest

    def take_left(self, w: float, gap: float = 0.0) -> tuple["Box", "Box"]:
        left = Box(self.x, self.y, w, self.h)
        rest = Box(self.x + w + gap, self.y, max(0.0, self.w - w - gap), self.h)
        return left, rest

    def split_h(self, n: int = 2, gap: float = 0.0, ratios: Iterable[float] | None = None) -> list["Box"]:
        """横に n 分割。ratios 指定時はその比率で分ける。"""
        ratios = list(ratios) if ratios else [1.0] * n
        n = len(ratios)
        total = sum(ratios)
        usable = self.w - gap * (n - 1)
        out, cursor = [], self.x
        for r in ratios:
            w = usable * (r / total)
            out.append(Box(cursor, self.y, w, self.h))
            cursor += w + gap
        return out

    def split_v(self, n: int = 2, gap: float = 0.0, ratios: Iterable[float] | None = None) -> list["Box"]:
        """縦に n 分割。"""
        ratios = list(ratios) if ratios else [1.0] * n
        n = len(ratios)
        total = sum(ratios)
        usable = self.h - gap * (n - 1)
        out, cursor = [], self.y
        for r in ratios:
            h = usable * (r / total)
            out.append(Box(self.x, cursor, self.w, h))
            cursor += h + gap
        return out

    def grid(self, rows: int, cols: int, gap_x: float = 0.0, gap_y: float = 0.0) -> list[list["Box"]]:
        return [row.split_h(cols, gap_x) for row in self.split_v(rows, gap_y)]

    def overlaps(self, other: "Box", tol: float = 0.0) -> bool:
        return not (
            self.right <= other.x + tol
            or other.right <= self.x + tol
            or self.bottom <= other.y + tol
            or other.bottom <= self.y + tol
        )

    def intersection_area(self, other: "Box") -> float:
        dx = min(self.right, other.right) - max(self.x, other.x)
        dy = min(self.bottom, other.bottom) - max(self.y, other.y)
        return dx * dy if dx > 0 and dy > 0 else 0.0

    @property
    def area(self) -> float:
        return self.w * self.h

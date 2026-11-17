"""レンダラの共通インタフェースと自動選択。

優先順位:
  1. PowerPoint COM（Windows、PowerPoint がインストール済み）… 実際の見た目と一致
  2. LibreOffice（+ PDF → PNG 変換手段）… フォント代替や図形の差異が出る可能性あり

描画差異は review レポートに明記する（どのレンダラで検査したかを残す）。
"""

from __future__ import annotations

import platform
import shutil
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RenderResult:
    images: list[Path] = field(default_factory=list)
    renderer: str = ""
    fidelity: str = "unknown"      # native | approximate
    notes: list[str] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.images)


class RendererUnavailable(RuntimeError):
    pass


def available_renderers() -> list[str]:
    out: list[str] = []
    if platform.system() == "Windows":
        try:
            import win32com.client  # noqa: F401

            out.append("powerpoint")
        except Exception:  # noqa: BLE001
            pass
    if _soffice_path():
        out.append("libreoffice")
    return out


def _soffice_path() -> str | None:
    found = shutil.which("soffice") or shutil.which("soffice.exe")
    if found:
        return found
    for cand in (
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/usr/bin/soffice",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    ):
        if Path(cand).exists():
            return cand
    return None


def render_pptx(
    pptx: str | Path,
    out_dir: str | Path,
    *,
    renderer: str = "auto",
    width: int = 1600,
    height: int | None = None,
    slides: list[int] | None = None,
) -> RenderResult:
    """PPTX の各ページを PNG に書き出す。"""
    pptx = Path(pptx).resolve()
    if not pptx.exists():
        raise FileNotFoundError(pptx)
    from pptx import Presentation
    prs = Presentation(str(pptx))
    if width <= 0 or (height is not None and height <= 0):
        raise ValueError("画像サイズは正の数にしてください")
    if slides is not None:
        if not slides or any(i < 1 or i > len(prs.slides) for i in slides):
            raise ValueError(f"slides は1〜{len(prs.slides)}のページ番号で指定してください")
    height = height or round(width * prs.slide_height / prs.slide_width)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    order = available_renderers() if renderer == "auto" else [renderer]
    if not order:
        raise RendererUnavailable(
            "利用可能なレンダラがありません。Windows では PowerPoint + pywin32、"
            "それ以外では LibreOffice（および PDF→PNG 変換手段）を用意してください。"
        )
    last_error: Exception | None = None
    for name in order:
        try:
            if name == "powerpoint":
                from .powerpoint_com import render as render_com

                return render_com(pptx, out_dir, width=width, height=height, slides=slides)
            if name == "libreoffice":
                from .libreoffice import render as render_lo

                return render_lo(pptx, out_dir, width=width, slides=slides)
            raise RendererUnavailable(f"unknown renderer {name!r}")
        except Exception as exc:  # noqa: BLE001 - 次の候補にフォールバックする
            last_error = exc
    raise RendererUnavailable(f"レンダリングに失敗しました: {last_error}")

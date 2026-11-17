"""LibreOffice 経由のレンダリング（Windows 以外、または PowerPoint が無い環境）。

PPTX -> PDF -> PNG の 2 段で変換する。PDF -> PNG には PyMuPDF または
pdftoppm のいずれかが必要。フォント代替や一部図形の描画差異が出る可能性があるため、
fidelity="approximate" を返し、レビュー報告に差異の可能性を明記する。
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from .base import RenderResult, RendererUnavailable, _soffice_path

APPROX_NOTE = (
    "LibreOffice 経由で描画しました。PowerPoint 実機とは"
    "フォント代替・行送り・図形の端部で差異が出る可能性があります。"
)


def render(
    pptx: Path,
    out_dir: Path,
    *,
    width: int = 1600,
    slides: list[int] | None = None,
) -> RenderResult:
    soffice = _soffice_path()
    if not soffice:
        raise RendererUnavailable("LibreOffice (soffice) が見つかりません")

    with tempfile.TemporaryDirectory() as tmp:
        profile = (Path(tmp) / "profile").as_uri()
        cmd = [soffice, f"-env:UserInstallation={profile}", "--headless", "--norestore", "--convert-to", "pdf",
               "--outdir", tmp, str(pptx)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        pdfs = list(Path(tmp).glob("*.pdf"))
        if proc.returncode != 0 or not pdfs:
            raise RendererUnavailable(
                f"PDF 変換に失敗しました: {proc.stdout} {proc.stderr}"
            )
        images = _pdf_to_png(pdfs[0], out_dir, width=width, slides=slides)
    return RenderResult(images=images, renderer="libreoffice", fidelity="approximate",
                        notes=[APPROX_NOTE])


def _pdf_to_png(pdf: Path, out_dir: Path, *, width: int, slides: list[int] | None) -> list[Path]:
    try:
        import pymupdf as fitz
    except Exception:
        fitz = None

    if fitz is not None:
        out: list[Path] = []
        doc = fitz.open(pdf)
        for i, page in enumerate(doc, start=1):
            if slides and i not in slides:
                continue
            zoom = width / page.rect.width
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            path = out_dir / f"slide{i:02d}.png"
            pix.save(str(path))
            out.append(path)
        doc.close()
        return out

    import shutil

    pdftoppm = shutil.which("pdftoppm")
    if pdftoppm:
        # Isolate temporary output so previous runs cannot enter this result.
        with tempfile.TemporaryDirectory() as png_tmp:
            subprocess.run(
                [pdftoppm, "-png", "-scale-to-x", str(width), "-scale-to-y", "-1",
                 str(pdf), str(Path(png_tmp) / "slide")],
                check=True, capture_output=True, timeout=300,
            )
            found = sorted(Path(png_tmp).glob("slide-*.png"), key=lambda p: int(p.stem.split('-')[-1]))
            renamed: list[Path] = []
            for p in found:
                idx = int(p.stem.split("-")[-1])
                if slides and idx not in slides:
                    continue
                target = out_dir / f"slide{idx:02d}.png"
                shutil.copyfile(p, target)
                renamed.append(target)
            return renamed

    raise RendererUnavailable(
        "PDF から PNG への変換手段がありません。PyMuPDF (pip install pymupdf) または "
        "poppler の pdftoppm を導入してください。"
    )

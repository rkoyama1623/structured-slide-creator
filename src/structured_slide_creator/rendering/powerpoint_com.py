"""PowerPoint COM によるネイティブレンダリング（Windows）。

実際に PowerPoint が描くピクセルなので、フォント・図形・表・グラフの見た目が
そのまま確認できる。視覚レビューはこちらを優先する。
"""

from __future__ import annotations

from pathlib import Path

from .base import RenderResult, RendererUnavailable

PPT_SAVE_AS_PNG = 18


def render(
    pptx: Path,
    out_dir: Path,
    *,
    width: int = 1600,
    height: int = 900,
    slides: list[int] | None = None,
) -> RenderResult:
    try:
        import pythoncom
        import win32com.client
    except Exception as exc:  # noqa: BLE001
        raise RendererUnavailable(f"pywin32 が利用できません: {exc}") from exc

    pythoncom.CoInitialize()
    app = None
    pres = None
    images: list[Path] = []
    notes: list[str] = []
    try:
        app = win32com.client.Dispatch("PowerPoint.Application")
        # PowerPoint は Visible=False を許さない場合があるため設定しない
        pres = app.Presentations.Open(
            str(pptx), ReadOnly=True, Untitled=False, WithWindow=False
        )
        total = pres.Slides.Count
        targets = slides or list(range(1, total + 1))
        for i in targets:
            if i < 1 or i > total:
                notes.append(f"スライド {i} は存在しません（全 {total} 枚）")
                continue
            path = out_dir / f"slide{i:02d}.png"
            pres.Slides(i).Export(str(path.resolve()), "PNG", width, height)
            images.append(path)
    except Exception as exc:  # noqa: BLE001
        raise RendererUnavailable(f"PowerPoint COM でのレンダリングに失敗: {exc}") from exc
    finally:
        try:
            if pres is not None:
                pres.Close()
        except Exception:  # noqa: BLE001
            pass
        try:
            if app is not None:
                app.Quit()
        except Exception:  # noqa: BLE001
            pass
        pythoncom.CoUninitialize()

    return RenderResult(images=images, renderer="powerpoint", fidelity="native", notes=notes)

"""Write machine-readable and human-readable review artifacts."""

import hashlib
import json
import os
from pathlib import Path

from ..rendering import RendererUnavailable, render_pptx
from .checks import check_pptx


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_review_bindings(report):
    """Return changed/missing bindings; an empty list is NOT visual approval."""
    if not isinstance(report, dict):
        report = json.loads(Path(report).read_text(encoding="utf-8"))
    entries = [{"path": report["pptx"], "sha256": report.get("pptx_sha256")}]
    entries += report.get("images", []) + report.get("sources", [])
    differences = []
    for item in entries:
        path = Path(item["path"])
        if not item.get("sha256"):
            differences.append(f"unbound: {path}")
        elif not path.is_file():
            differences.append(f"missing: {path}")
        elif file_sha256(path) != item["sha256"]:
            differences.append(f"changed: {path}")
    return differences


def review_pptx(
    path, out_dir, *, theme="neutral", render=True, renderer="auto", sources=None
):
    path, out_dir = Path(path), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    initial_hash = file_sha256(path)
    source_records = [
        {"path": str(Path(p).resolve()), "sha256": file_sha256(p)}
        for p in (sources or [])
    ]
    findings = check_pptx(path, theme)
    result = {
        "pptx": str(path.resolve()),
        "pptx_sha256": initial_hash,
        "artifact_status": "stable",
        "sources": source_records,
        "source_review": "pending" if source_records else "not_requested",
        "theme": getattr(theme, "name", str(theme)),
        "findings": [f.to_dict() for f in findings],
        "renderer": None,
        "fidelity": None,
        "notes": [],
        "images": [],
        "visual_review": "pending" if render else "not_requested",
    }
    if render:
        try:
            rendered = render_pptx(path, out_dir / "slides", renderer=renderer)
            result.update(
                renderer=rendered.renderer,
                fidelity=rendered.fidelity,
                images=[
                    {
                        "slide": int(p.stem.removeprefix("slide")),
                        "path": str(p.resolve()),
                        "sha256": file_sha256(p),
                    }
                    for p in rendered.images
                ],
                notes=rendered.notes,
            )
        except RendererUnavailable as exc:
            result["notes"].append(str(exc))
            result["visual_review"] = "unavailable"
    result["pptx_sha256_after"] = file_sha256(path) if path.is_file() else None
    differences = verify_review_bindings(result)
    if differences:
        result["artifact_status"] = "stale"
        result["visual_review"] = "stale"
        result["notes"].append(
            "Artifacts changed during review: " + "; ".join(differences)
        )
    (out_dir / "review.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "images.json").write_text(
        json.dumps(result["images"], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# スライド品質検査",
        "",
        f"対象: {path.name}",
        f"PPTX SHA-256: {result['pptx_sha256']}",
        f"Artifact binding: {result['artifact_status']}; source review: {result['source_review']}",
        f"検出: {len(findings)} 件 / renderer: {result['renderer'] or 'なし'}",
        "",
        "文字あふれ・重なり・整列は推定です。画像による視覚レビューは別途必要です。",
        "",
    ]
    lines += [f"- {note}" for note in result["notes"]]
    lines += [
        f"- **{f.severity}** slide {f.slide} / {f.shape} / {f.kind}: {f.message}"
        for f in findings
    ]
    if source_records:
        lines += ["", "## Explicit sources (review pending)", ""]
        lines += [f"- {s['path']} — SHA-256 `{s['sha256']}`" for s in source_records]
    lines += ["", "## 画像", ""]
    lines += [
        f"- [slide {im['slide']}]({os.path.relpath(im['path'], out_dir.resolve())}) — SHA-256 `{im['sha256']}`"
        for im in result["images"]
    ]
    (out_dir / "review.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result

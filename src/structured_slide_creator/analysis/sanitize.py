"""Allowlist serialization: no text, filenames, object names, fonts or source colors."""

from hashlib import sha256
from pathlib import Path
import json
import unicodedata
from PIL import Image, ImageDraw
from .brand import brand_flags
from .classify import classify_slide


def sanitize_deck(raw):
    w, h = raw["width"], raw["height"]
    slides = []
    for slide in raw["slides"]:
        shapes = []
        for s in slide["shapes"]:
            text = s.get("text", "")
            shapes.append(
                {
                    "id": s["id"],
                    "kind": s["kind"],
                    "box": s["box"],
                    "text_length": len(text),
                    "wide_chars": sum(
                        unicodedata.east_asian_width(c) in ("W", "F") for c in text
                    ),
                    "font_sizes": sorted(
                        {r["size"] for r in s["runs"] if r["size"] is not None}
                    ),
                    "levels": s["levels"],
                    "brand_flags": brand_flags(s, w, h),
                    "inherit": False if s["kind"] == "image" else None,
                }
            )
        # Union coverage on a normalized occupancy grid (also usable for layout similarity).
        grid = []
        for y in range(6):
            for x in range(12):
                grid.append(
                    int(
                        any(
                            s["box"]["x"]
                            <= (x + 0.5) * w / 12
                            <= s["box"]["x"] + s["box"]["w"]
                            and s["box"]["y"]
                            <= (y + 0.5) * h / 6
                            <= s["box"]["y"] + s["box"]["h"]
                            for s in shapes
                            if s["kind"] not in ("group", "connector")
                        )
                    )
                )
        slides.append(
            {
                "index": slide["index"],
                "classification": classify_slide(slide, w, h),
                "shapes": shapes,
                "inherited_images": slide["inherited_images"],
                "density": {
                    "characters": sum(s["text_length"] for s in shapes),
                    "shape_count": len(shapes),
                    "occupancy": sum(grid) / len(grid),
                },
                "occupancy_grid": grid,
            }
        )
    return {"schema_version": 1, "width": w, "height": h, "slides": slides}


def deck_id(sanitized):
    return sha256(json.dumps(sanitized, sort_keys=True).encode()).hexdigest()[:16]


def wireframe(deck, slide, path):
    width = 960
    height = round(width * deck["height"] / deck["width"])
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    for shape in slide["shapes"]:
        b = shape["box"]
        xy = tuple(
            round(v * width / deck["width"])
            for v in (b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"])
        )
        if xy[2] < xy[0] or xy[3] < xy[1]:
            continue
        draw.rectangle(xy, outline="#687786", width=2)
        draw.text((xy[0] + 3, xy[1] + 3), shape["kind"], fill="#39414A")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path


def validate_sanitized(deck):
    """Reject raw/nonconforming data before catalog ingestion."""
    if (
        not isinstance(deck, dict)
        or set(deck) != {"schema_version", "width", "height", "slides"}
        or deck["schema_version"] != 1
    ):
        raise ValueError("匿名化スキーマのJSONを指定してください")
    if not isinstance(deck["slides"], list):
        raise ValueError("slides must be a list")
    for slide in deck["slides"]:
        if set(slide) != {
            "index",
            "classification",
            "shapes",
            "inherited_images",
            "density",
            "occupancy_grid",
        }:
            raise ValueError("匿名化されていないスライドです")
        if set(slide["classification"]) != {"layout_type", "confidence", "evidence"}:
            raise ValueError("invalid classification")
        for shape in slide["shapes"]:
            if set(shape) != {
                "id",
                "kind",
                "box",
                "text_length",
                "wide_chars",
                "font_sizes",
                "levels",
                "brand_flags",
                "inherit",
            }:
                raise ValueError("匿名化されていない図形です")

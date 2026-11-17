"""Brand indicators are candidates, never automatic adoption decisions."""

import re

_BRAND = re.compile(r"株式会社|（株）|本部|センタ", re.IGNORECASE)


def brand_flags(shape, width, height):
    reasons = []
    if _BRAND.search(shape.get("text", "")):
        reasons.append("organization_text_candidate")
    if shape["kind"] == "image":
        reasons.append("image_rights_unverified")
        b = shape["box"]
        if b["w"] * b["h"] < width * height * 0.06 and (
            b["x"] < width * 0.15 or b["x"] + b["w"] > width * 0.85
        ):
            reasons.append("corner_logo_candidate")
    return [
        {"reason": reason, "inherit": False, "needs_human_review": True}
        for reason in reasons
    ]

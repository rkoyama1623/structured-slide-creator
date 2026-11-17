"""Human decisions survive repeated catalog merges."""

from pathlib import Path
import yaml
from ..generation.layouts import catalog_entries
from .sanitize import deck_id, validate_sanitized


def export_catalog(path):
    entries = [
        {**entry, "status": "accepted", "source": "builtin"}
        for entry in catalog_entries()
    ]
    return _save(path, {"schema_version": 1, "entries": entries})


def merge_catalog(path, decks):
    path = Path(path)
    catalog = (
        yaml.safe_load(path.read_text(encoding="utf-8"))
        if path.exists()
        else {"schema_version": 1, "entries": []}
    )
    existing = {e["id"]: e for e in catalog["entries"]}
    for deck in decks:
        validate_sanitized(deck)
        did = deck_id(deck)
        for slide in deck["slides"]:
            sid = f"observed-{did}-{slide['index']:03d}"
            if sid not in existing:
                existing[sid] = {
                    "id": sid,
                    "status": "proposed",
                    "source": "sanitized",
                    **slide["classification"],
                    "density": slide["density"],
                    "occupancy_grid": slide["occupancy_grid"],
                    "needs_human_review": True,
                }
    catalog["entries"] = list(existing.values())
    return _save(path, catalog)


def tune_catalog(path, entry_id, status, comment=""):
    if status not in ("accepted", "rejected", "revise", "proposed"):
        raise ValueError("invalid catalog status")
    path = Path(path)
    catalog = yaml.safe_load(path.read_text(encoding="utf-8"))
    entry = next((e for e in catalog["entries"] if e["id"] == entry_id), None)
    if entry is None:
        raise ValueError(f"catalog entry not found: {entry_id}")
    entry.update(
        status=status,
        comment=comment,
        needs_human_review=status in ("revise", "proposed"),
    )
    return _save(path, catalog)


def _save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return path

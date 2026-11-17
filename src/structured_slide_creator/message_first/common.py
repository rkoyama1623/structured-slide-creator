"""Strict input types shared by the separate story/layout artifacts."""

import json
import math
from dataclasses import dataclass
from pathlib import Path

import yaml

from ..plan.schema import PlanIssue


@dataclass
class Document:
    data: dict
    path: Path | None = None

    @property
    def source_dir(self):
        return self.path.parent if self.path else Path.cwd()

    def resolve(self, value):
        path = Path(value).expanduser()
        return (
            path.resolve() if path.is_absolute() else (self.source_dir / path).resolve()
        )


def read_document(path):
    path = Path(path).resolve()
    if path.suffix.lower() not in {".yaml", ".yml", ".json"}:
        raise ValueError("expected a .yaml, .yml or .json document")
    value = (
        json.loads(path.read_text(encoding="utf-8"))
        if path.suffix.lower() == ".json"
        else yaml.safe_load(path.read_text(encoding="utf-8"))
    )
    if not isinstance(value, dict):
        raise TypeError("document root must be a mapping")
    return Document(value, path)


def mapping(value, where):
    if not isinstance(value, dict):
        raise TypeError(f"{where} must be a mapping")
    return value


def string(value, where):
    if not isinstance(value, str):
        raise TypeError(f"{where} must be a string")
    return value


def number(value, where):
    try:
        valid = (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(value)
        )
    except OverflowError:
        valid = False
    if not valid:
        raise TypeError(f"{where} must be a finite representable number (not boolean)")
    return value


def records(value, where):
    if not isinstance(value, list):
        raise TypeError(f"{where} must be a list")
    for i, item in enumerate(value):
        mapping(item, f"{where}[{i}]")
    return value


def strings(value, where):
    if not isinstance(value, list):
        raise TypeError(f"{where} must be a list of strings")
    for i, item in enumerate(value):
        string(item, f"{where}[{i}]")
    return value


def required_text(record, keys, where, issues):
    for key in keys:
        if not record.get(key, "").strip():
            issues.append(
                PlanIssue("error", where, f"{key} is required and must not be empty")
            )


def identifiers(items, where, issues):
    seen = set()
    for i, item in enumerate(items):
        ident = item.get("id", "")
        required_text(item, ["id"], f"{where}[{i}]", issues)
        if ident in seen:
            issues.append(PlanIssue("error", where, f"duplicate id {ident!r}"))
        seen.add(ident)
    return seen


def has_errors(issues):
    return any(i.level == "error" for i in issues)

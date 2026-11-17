"""Resolve editable-checkout assets and assets bundled in wheels."""

from pathlib import Path


def asset_root():
    checkout = Path(__file__).resolve().parents[2]
    return (
        checkout
        if (checkout / "pyproject.toml").is_file()
        else Path(__file__).parent / "_assets"
    )

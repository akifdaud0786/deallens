"""Public read-only composition (ADR 0005). Imports only the projection reader: no SerpApi, no collector."""
from __future__ import annotations

from pathlib import Path

from deallens.projection import ProjectionReader

PROJECTION = Path("data/projection/deallens.sqlite")


def open_public_reader(root) -> ProjectionReader:
    return ProjectionReader(Path(root) / PROJECTION)


def projection_status(root) -> str:
    """'missing' (never built), 'empty' (built, no observations) or 'ready'. Reports; never invents data."""
    if not (Path(root) / PROJECTION).exists():
        return "missing"
    return "ready" if open_public_reader(root).info().get("observations") else "empty"

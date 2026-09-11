"""Loads the researched expo catalogue (data/expo/events.json).

The JSON is the single source of truth: the scoring engine, the planner, the
ICS export, the dashboard and the live artifact all read from it.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from config.settings import settings

CATALOG_PATH = settings.data_dir / "expo" / "events.json"


@lru_cache(maxsize=1)
def _load(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_catalog(path: Path | None = None) -> dict[str, Any]:
    return _load(str(path or CATALOG_PATH))


def list_events(path: Path | None = None) -> list[dict[str, Any]]:
    return sorted(load_catalog(path)["events"], key=lambda e: (e["start"], e["end"]))


def get_event(event_id: str, path: Path | None = None) -> dict[str, Any] | None:
    for ev in load_catalog(path)["events"]:
        if ev["id"] == event_id:
            return ev
    return None


def meta(path: Path | None = None) -> dict[str, Any]:
    return load_catalog(path)["_meta"]


def reload() -> None:
    _load.cache_clear()

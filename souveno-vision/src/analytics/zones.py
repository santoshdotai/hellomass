"""Zone / virtual line definitions (normalised coordinates, saved per source)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from typing import Any

from src.analytics.geometry import validate_line, validate_polygon

ZONE_KINDS = {
    "roi": "Region of interest",
    "restricted": "Restricted zone",
    "occupancy": "Occupancy zone",
    "line": "Virtual line",
}

DEFAULT_COLORS = {"roi": "#40a9ff", "restricted": "#ff4d4f", "occupancy": "#36cfc9", "line": "#ffd666"}


@dataclass
class Zone:
    name: str
    kind: str
    points: list[list[float]]
    zone_id: str = field(default_factory=lambda: f"Z-{uuid.uuid4().hex[:8].upper()}")
    color: str = ""
    enabled: bool = True
    dwell_threshold_seconds: float | None = None   # overrides the rule default for this zone
    occupancy_limit: int | None = None              # overrides the rule default for this zone
    direction_flipped: bool = False                 # lines: swap in/out
    in_label: str = "Entry"
    out_label: str = "Exit"

    def __post_init__(self):
        self.kind = (self.kind or "roi").lower()
        if not self.color:
            self.color = DEFAULT_COLORS.get(self.kind, "#40a9ff")
        self.points = [[float(p[0]), float(p[1])] for p in self.points]

    @property
    def is_line(self) -> bool:
        return self.kind == "line"

    def validate(self, min_area: float = 0.001) -> list[str]:
        if self.kind not in ZONE_KINDS:
            return [f"Unknown zone kind '{self.kind}'"]
        if not self.name or not self.name.strip():
            return ["Zone name is required"]
        return validate_line(self.points) if self.is_line else validate_polygon(self.points, min_area)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Zone":
        allowed = {k for k in cls.__dataclass_fields__}
        data = {k: v for k, v in d.items() if k in allowed}
        if "kind" not in data and "zone_type" in d:
            data["kind"] = d["zone_type"]
        if "zone_id" in data and not data["zone_id"]:
            data.pop("zone_id")
        return cls(**data)


def validate_zones(zones: list[Zone], min_area: float = 0.001) -> dict[str, list[str]]:
    problems = {}
    names = [z.name.strip().lower() for z in zones]
    for z in zones:
        p = z.validate(min_area)
        if names.count(z.name.strip().lower()) > 1:
            p.append("Zone names must be unique")
        if p:
            problems[z.name or z.zone_id] = p
    return problems

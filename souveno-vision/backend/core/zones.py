"""Zone Engine (Phase 4/5) — tracks zone membership, dwell time, and
entrance-line crossings using normalized (0..1) coordinates so a saved
zone layout works at any video resolution."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from backend.core.geometry import point_in_polygon, line_crossing_direction

Point = tuple[float, float]


@dataclass
class ZoneDef:
    zone_id: str
    name: str
    zone_type: str  # COUNTER_ZONE | QUEUE_ZONE | DINING_ZONE | PREP_ZONE | PICKUP_ZONE | ENTRANCE_LINE | TABLE
    shape_type: str  # "polygon" | "line"
    points: list[Point]  # normalized 0..1
    color: str = "#3ba7ff"


@dataclass
class ZoneUpdateResult:
    zones_entered: list[str] = field(default_factory=list)
    zones_exited: list[str] = field(default_factory=list)
    zones_now: set[str] = field(default_factory=set)
    line_crossings: list[dict] = field(default_factory=list)  # [{"zone_id":..,"direction":"enter"/"exit"}]


class ZoneEngine:
    """Stateless with respect to geometry, stateful with respect to
    per-track membership/dwell so it can report enter/exit transitions."""

    def __init__(self, zones: list[ZoneDef]):
        self.zones = zones
        self.polygon_zones = [z for z in zones if z.shape_type == "polygon"]
        self.line_zones = [z for z in zones if z.shape_type == "line"]
        self._track_zones: dict[int, set[str]] = {}
        self._zone_entry_time: dict[tuple[int, str], float] = {}
        self._prev_point: dict[int, Point] = {}

    def zone_by_id(self, zone_id: str) -> Optional[ZoneDef]:
        return next((z for z in self.zones if z.zone_id == zone_id), None)

    def zones_of_type(self, zone_type: str) -> list[ZoneDef]:
        return [z for z in self.zones if z.zone_type == zone_type]

    def update(self, track_id: int, point: Point, timestamp: float) -> ZoneUpdateResult:
        result = ZoneUpdateResult()
        currently_in = set()
        for zone in self.polygon_zones:
            if point_in_polygon(point, zone.points):
                currently_in.add(zone.zone_id)

        previously_in = self._track_zones.get(track_id, set())
        entered = currently_in - previously_in
        exited = previously_in - currently_in

        for zone_id in entered:
            self._zone_entry_time[(track_id, zone_id)] = timestamp
        for zone_id in exited:
            self._zone_entry_time.pop((track_id, zone_id), None)

        self._track_zones[track_id] = currently_in
        result.zones_entered = sorted(entered)
        result.zones_exited = sorted(exited)
        result.zones_now = currently_in

        prev_point = self._prev_point.get(track_id)
        if prev_point is not None:
            for line_zone in self.line_zones:
                if len(line_zone.points) >= 2:
                    direction = line_crossing_direction(line_zone.points[0], line_zone.points[1], prev_point, point)
                    if direction:
                        result.line_crossings.append({"zone_id": line_zone.zone_id, "direction": direction})
        self._prev_point[track_id] = point

        return result

    def dwell_seconds(self, track_id: int, zone_id: str, timestamp: float) -> float:
        entry = self._zone_entry_time.get((track_id, zone_id))
        if entry is None:
            return 0.0
        return max(0.0, timestamp - entry)

    def zone_occupants(self) -> dict[str, set[int]]:
        occupants: dict[str, set[int]] = {z.zone_id: set() for z in self.polygon_zones}
        for track_id, zone_ids in self._track_zones.items():
            for zone_id in zone_ids:
                occupants.setdefault(zone_id, set()).add(track_id)
        return occupants

    def forget_track(self, track_id: int):
        self._track_zones.pop(track_id, None)
        self._prev_point.pop(track_id, None)
        keys = [k for k in self._zone_entry_time if k[0] == track_id]
        for k in keys:
            self._zone_entry_time.pop(k, None)


def zone_defs_from_records(records: list[dict]) -> list[ZoneDef]:
    """records: list of {"zone_id"/"name","zone_type","shape_type","points","color"}"""
    return [
        ZoneDef(
            zone_id=r.get("zone_id") or r["name"],
            name=r["name"],
            zone_type=r["zone_type"],
            shape_type=r.get("shape_type", "polygon"),
            points=[tuple(p) for p in r["points"]],
            color=r.get("color", "#3ba7ff"),
        )
        for r in records
    ]


DEFAULT_ZONE_PRESET = "default_cafe_layout"

DEFAULT_ZONES: list[dict] = [
    {"name": "Counter", "zone_type": "COUNTER_ZONE", "shape_type": "polygon",
     "points": [[0.35, 0.35], [0.65, 0.35], [0.65, 0.55], [0.35, 0.55]], "color": "#3ba7ff"},
    {"name": "Queue", "zone_type": "QUEUE_ZONE", "shape_type": "polygon",
     "points": [[0.05, 0.4], [0.35, 0.4], [0.35, 0.75], [0.05, 0.75]], "color": "#f5a623"},
    {"name": "Dining", "zone_type": "DINING_ZONE", "shape_type": "polygon",
     "points": [[0.02, 0.05], [0.98, 0.05], [0.98, 0.3], [0.02, 0.3]], "color": "#7ed957"},
    {"name": "Prep", "zone_type": "PREP_ZONE", "shape_type": "polygon",
     "points": [[0.65, 0.1], [0.95, 0.1], [0.95, 0.45], [0.65, 0.45]], "color": "#d93bff"},
    {"name": "Pickup", "zone_type": "PICKUP_ZONE", "shape_type": "polygon",
     "points": [[0.4, 0.55], [0.6, 0.55], [0.6, 0.7], [0.4, 0.7]], "color": "#ff5b5b"},
    {"name": "Entrance", "zone_type": "ENTRANCE_LINE", "shape_type": "line",
     "points": [[0.0, 0.85], [1.0, 0.85]], "color": "#ffffff"},
]

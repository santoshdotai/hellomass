"""Layer 5 — polygon zone membership with enter/exit hysteresis and occupancy counts."""
from __future__ import annotations

from dataclasses import dataclass, field

from src.analytics.geometry import Point, point_in_polygon
from src.analytics.zones import Zone


@dataclass
class ZoneTransition:
    zone_id: str
    zone_name: str
    zone_kind: str
    track_id: int
    timestamp: float


@dataclass
class ZoneUpdate:
    entered: list[ZoneTransition] = field(default_factory=list)
    exited: list[ZoneTransition] = field(default_factory=list)
    inside: set[str] = field(default_factory=set)  # zone_ids the track is confirmed inside


class ZoneOccupancy:
    """Per-track membership with N-frame hysteresis so a foot point wobbling on a
    boundary does not generate enter/exit storms."""

    def __init__(self, zones: list[Zone], enter_frames: int = 2, exit_frames: int = 3):
        self.zones = [z for z in zones if not z.is_line and z.enabled]
        self.enter_frames = max(1, int(enter_frames))
        self.exit_frames = max(1, int(exit_frames))
        self._inside: dict[int, set[str]] = {}
        self._streak: dict[tuple[int, str], int] = {}   # +n consecutive inside, -n consecutive outside
        self.entered_at: dict[tuple[int, str], float] = {}

    def zone(self, zone_id: str) -> Zone | None:
        return next((z for z in self.zones if z.zone_id == zone_id), None)

    def update(self, track_id: int, point: Point, timestamp: float) -> ZoneUpdate:
        result = ZoneUpdate()
        inside_now = self._inside.setdefault(track_id, set())
        for zone in self.zones:
            key = (track_id, zone.zone_id)
            raw_inside = point_in_polygon(point, [(p[0], p[1]) for p in zone.points])
            streak = self._streak.get(key, 0)
            streak = (streak + 1 if streak >= 0 else 1) if raw_inside else (streak - 1 if streak <= 0 else -1)
            self._streak[key] = streak
            confirmed = zone.zone_id in inside_now
            if not confirmed and streak >= self.enter_frames:
                inside_now.add(zone.zone_id)
                self.entered_at[key] = timestamp
                result.entered.append(ZoneTransition(zone.zone_id, zone.name, zone.kind, track_id, timestamp))
            elif confirmed and streak <= -self.exit_frames:
                inside_now.discard(zone.zone_id)
                self.entered_at.pop(key, None)
                result.exited.append(ZoneTransition(zone.zone_id, zone.name, zone.kind, track_id, timestamp))
        result.inside = set(inside_now)
        return result

    def dwell_seconds(self, track_id: int, zone_id: str, timestamp: float) -> float:
        start = self.entered_at.get((track_id, zone_id))
        return max(0.0, timestamp - start) if start is not None else 0.0

    def occupants(self) -> dict[str, set[int]]:
        out: dict[str, set[int]] = {z.zone_id: set() for z in self.zones}
        for tid, zone_ids in self._inside.items():
            for zid in zone_ids:
                out.setdefault(zid, set()).add(tid)
        return out

    def counts(self) -> dict[str, int]:
        return {zid: len(s) for zid, s in self.occupants().items()}

    def forget(self, track_id: int, timestamp: float | None = None) -> list[ZoneTransition]:
        """Drop a lost track; returns synthetic exit transitions for zones it was inside."""
        exits = []
        for zid in self._inside.pop(track_id, set()):
            z = self.zone(zid)
            exits.append(ZoneTransition(zid, z.name if z else zid, z.kind if z else "roi", track_id, timestamp or 0.0))
            self.entered_at.pop((track_id, zid), None)
        for key in [k for k in self._streak if k[0] == track_id]:
            self._streak.pop(key, None)
        return exits

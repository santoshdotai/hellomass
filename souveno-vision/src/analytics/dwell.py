"""Layer 5 — dwell-time / loitering analytics on top of ZoneOccupancy."""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

from src.analytics.occupancy import ZoneOccupancy


@dataclass
class DwellAlert:
    zone_id: str
    zone_name: str
    track_id: int
    dwell_seconds: float
    threshold_seconds: float
    timestamp: float


class DwellTracker:
    """Reports a single alert per visit once the threshold is crossed, and keeps
    per-zone dwell statistics from completed visits."""

    def __init__(self, occupancy: ZoneOccupancy, default_threshold_seconds: float = 30.0, kinds=("restricted", "roi")):
        self.occupancy = occupancy
        self.default_threshold = float(default_threshold_seconds)
        self.kinds = set(kinds)
        self._alerted: set[tuple[int, str]] = set()
        self.completed: dict[str, list[float]] = {}
        self.active: dict[tuple[int, str], float] = {}

    def threshold_for(self, zone_id: str) -> float:
        z = self.occupancy.zone(zone_id)
        if z and z.dwell_threshold_seconds is not None and z.dwell_threshold_seconds > 0:
            return float(z.dwell_threshold_seconds)
        return self.default_threshold

    def set_default_threshold(self, seconds: float) -> None:
        self.default_threshold = float(seconds)

    def evaluate(self, track_id: int, inside: set[str], timestamp: float) -> list[DwellAlert]:
        alerts = []
        for zid in inside:
            zone = self.occupancy.zone(zid)
            if zone is None or (zone.kind not in self.kinds and not zone.dwell_threshold_seconds):
                continue
            dwell = self.occupancy.dwell_seconds(track_id, zid, timestamp)
            self.active[(track_id, zid)] = dwell
            threshold = self.threshold_for(zid)
            key = (track_id, zid)
            if dwell >= threshold and key not in self._alerted:
                self._alerted.add(key)
                alerts.append(DwellAlert(zid, zone.name, track_id, dwell, threshold, timestamp))
        return alerts

    def on_exit(self, track_id: int, zone_id: str, dwell_seconds: float) -> None:
        self._alerted.discard((track_id, zone_id))
        self.active.pop((track_id, zone_id), None)
        if dwell_seconds > 0:
            self.completed.setdefault(zone_id, []).append(dwell_seconds)

    def forget(self, track_id: int) -> None:
        for key in [k for k in self._alerted if k[0] == track_id]:
            self._alerted.discard(key)
        for key in [k for k in self.active if k[0] == track_id]:
            self.active.pop(key, None)

    def average_dwell(self, zone_id: str | None = None) -> float:
        samples = self.completed.get(zone_id, []) if zone_id else [v for vs in self.completed.values() for v in vs]
        samples = list(samples) + list(self.active.values())
        return float(mean(samples)) if samples else 0.0

    def reset_stats(self) -> None:
        self.completed.clear()

"""Spatial analytics orchestrator: feeds tracked people through zone
occupancy, dwell and line-crossing engines and emits one FrameAnalytics
snapshot per processed frame for the rules engine and the UI."""
from __future__ import annotations

from dataclasses import dataclass, field

from src.analytics.dwell import DwellAlert, DwellTracker
from src.analytics.geometry import normalize_point
from src.analytics.line_crossing import Crossing, LineCrossingCounter
from src.analytics.occupancy import ZoneOccupancy, ZoneTransition
from src.analytics.zones import Zone
from src.tracking.tracker import Track


@dataclass
class TrackView:
    track_id: int
    box: tuple[float, float, float, float]
    confidence: float
    zones: list[str]                 # zone_ids the track is inside
    zone_names: list[str]
    dwell: dict[str, float]          # zone_id -> seconds
    in_restricted: bool
    trail: list[tuple[int, int]]

    def to_dict(self) -> dict:
        return {"track_id": self.track_id, "label": f"Person {self.track_id}", "box": [round(v, 1) for v in self.box],
                "confidence": round(self.confidence, 2), "zones": self.zone_names,
                "dwell": {k: round(v, 1) for k, v in self.dwell.items()}, "in_restricted": self.in_restricted}


@dataclass
class FrameAnalytics:
    timestamp: float
    tracks: list[TrackView]
    entered: list[ZoneTransition]
    exited: list[ZoneTransition]
    crossings: list[Crossing]
    dwell_alerts: list[DwellAlert]
    zone_counts: dict[str, int]
    line_counts: dict
    people_visible: int
    entries: int
    exits: int
    occupancy: int
    zones: dict[str, Zone] = field(default_factory=dict)


class SpatialAnalytics:
    def __init__(self, zones: list[Zone], analytics_cfg: dict | None = None, default_dwell_seconds: float = 30.0):
        cfg = analytics_cfg or {}
        self.zones = zones
        self.zone_map = {z.zone_id: z for z in zones}
        self.occupancy = ZoneOccupancy(zones, int(cfg.get("zone_enter_frames", 2)), int(cfg.get("zone_exit_frames", 3)))
        self.lines = LineCrossingCounter(zones, float(cfg.get("line_debounce_seconds", 1.5)),
                                         float(cfg.get("line_side_margin", 0.004)))
        self.dwell = DwellTracker(self.occupancy, default_dwell_seconds)
        self._known: set[int] = set()
        self.has_line = any(z.is_line and z.enabled for z in zones)

    def reset_counts(self) -> None:
        self.lines.reset_counts()
        self.dwell.reset_stats()

    def update(self, tracks: list[Track], width: int, height: int, timestamp: float) -> FrameAnalytics:
        entered: list[ZoneTransition] = []
        exited: list[ZoneTransition] = []
        crossings: list[Crossing] = []
        dwell_alerts: list[DwellAlert] = []
        views: list[TrackView] = []
        current_ids = set()
        for tr in tracks:
            current_ids.add(tr.track_id)
            self._known.add(tr.track_id)
            point = normalize_point(tr.bottom_center, width, height)
            zu = self.occupancy.update(tr.track_id, point, timestamp)
            entered.extend(zu.entered)
            for ex in zu.exited:
                self.dwell.on_exit(ex.track_id, ex.zone_id, timestamp - self.occupancy.entered_at.get((ex.track_id, ex.zone_id), timestamp))
            exited.extend(zu.exited)
            crossings.extend(self.lines.update(tr.track_id, point, timestamp))
            dwell_alerts.extend(self.dwell.evaluate(tr.track_id, zu.inside, timestamp))
            dwell = {zid: self.occupancy.dwell_seconds(tr.track_id, zid, timestamp) for zid in zu.inside}
            views.append(TrackView(tr.track_id, tr.box, tr.confidence, sorted(zu.inside),
                                   [self.zone_map[z].name for z in sorted(zu.inside) if z in self.zone_map], dwell,
                                   any(self.zone_map[z].kind == "restricted" for z in zu.inside if z in self.zone_map),
                                   list(tr.trail)))
        # tracks that disappeared this frame stay registered until the pipeline calls forget() on tracker expiry
        totals = self.lines.totals()
        occupancy = max(0, totals["in"] - totals["out"]) if self.has_line else len(views)
        return FrameAnalytics(timestamp=timestamp, tracks=views, entered=entered, exited=exited, crossings=crossings,
                              dwell_alerts=dwell_alerts, zone_counts=self.occupancy.counts(),
                              line_counts=self.lines.snapshot(), people_visible=len(views), entries=totals["in"],
                              exits=totals["out"], occupancy=occupancy, zones=self.zone_map)

    def forget(self, track_id: int, timestamp: float) -> list[ZoneTransition]:
        exits = self.occupancy.forget(track_id, timestamp)
        for ex in exits:
            self.dwell.on_exit(track_id, ex.zone_id, 0.0)
        self.lines.forget(track_id)
        self.dwell.forget(track_id)
        self._known.discard(track_id)
        return exits

    def forget_all(self) -> None:
        for tid in list(self._known):
            self.forget(tid, 0.0)

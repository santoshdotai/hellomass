"""Layer 5 — directional virtual-line crossing with jitter debouncing.

A crossing is counted only when a track's foot point moves from a *confirmed*
side of the line to the other confirmed side (points within `side_margin` of
the line are undecided, so boundary jitter never flips the side), the movement
segment actually intersects the finite line, and the same track has not crossed
this line within `debounce_seconds`.

Direction convention: with the line drawn from point A to point B, moving from
the right-hand side of A->B to the left-hand side is "in" (Entry). The zone
editor offers a flip toggle which swaps the labels."""
from __future__ import annotations

from dataclasses import dataclass

from src.analytics.geometry import Point, segments_intersect, side_of_line
from src.analytics.zones import Zone


@dataclass
class Crossing:
    zone_id: str
    zone_name: str
    track_id: int
    direction: str          # "in" | "out"
    label: str              # zone.in_label / zone.out_label
    timestamp: float


class LineCrossingCounter:
    def __init__(self, lines: list[Zone], debounce_seconds: float = 1.5, side_margin: float = 0.004):
        self.lines = [z for z in lines if z.is_line and z.enabled]
        self.debounce = float(debounce_seconds)
        self.side_margin = float(side_margin)
        self._side: dict[tuple[str, int], int] = {}
        self._last_point: dict[int, Point] = {}
        self._last_cross: dict[tuple[str, int], float] = {}
        self.counts: dict[str, dict[str, int]] = {z.zone_id: {"in": 0, "out": 0} for z in self.lines}

    def reset_counts(self) -> None:
        for c in self.counts.values():
            c["in"] = 0
            c["out"] = 0

    def totals(self) -> dict[str, int]:
        return {"in": sum(c["in"] for c in self.counts.values()), "out": sum(c["out"] for c in self.counts.values())}

    def update(self, track_id: int, point: Point, timestamp: float) -> list[Crossing]:
        crossings: list[Crossing] = []
        prev_point = self._last_point.get(track_id)
        for line in self.lines:
            a, b = (line.points[0][0], line.points[0][1]), (line.points[1][0], line.points[1][1])
            key = (line.zone_id, track_id)
            side = side_of_line(a, b, point, self.side_margin)
            prev_side = self._side.get(key, 0)
            if side == 0:
                continue  # undecided: on/near the line, keep the last confirmed side
            if prev_side == 0:
                self._side[key] = side
                continue
            if side != prev_side:
                crossed = prev_point is not None and segments_intersect(prev_point, point, a, b)
                if not crossed and prev_point is not None:
                    # fast movers may skip past the finite segment; accept if the projection lies within it
                    crossed = self._projection_within(a, b, point) or self._projection_within(a, b, prev_point)
                last = self._last_cross.get(key, -1e9)
                if crossed and timestamp - last >= self.debounce:
                    # right(-1) -> left(+1) of A->B is "in" unless the line is flipped
                    direction = "in" if (prev_side < 0 < side) != line.direction_flipped else "out"
                    self.counts.setdefault(line.zone_id, {"in": 0, "out": 0})[direction] += 1
                    self._last_cross[key] = timestamp
                    crossings.append(Crossing(line.zone_id, line.name, track_id, direction,
                                              line.in_label if direction == "in" else line.out_label, timestamp))
                self._side[key] = side
        self._last_point[track_id] = point
        return crossings

    @staticmethod
    def _projection_within(a: Point, b: Point, p: Point) -> bool:
        abx, aby = b[0] - a[0], b[1] - a[1]
        length_sq = abx * abx + aby * aby
        if length_sq == 0:
            return False
        t = ((p[0] - a[0]) * abx + (p[1] - a[1]) * aby) / length_sq
        return -0.05 <= t <= 1.05

    def forget(self, track_id: int) -> None:
        self._last_point.pop(track_id, None)
        for key in [k for k in self._side if k[1] == track_id]:
            self._side.pop(key, None)
        for key in [k for k in self._last_cross if k[1] == track_id]:
            self._last_cross.pop(key, None)

    def snapshot(self) -> dict:
        return {"lines": {z.zone_id: {"name": z.name, **self.counts.get(z.zone_id, {"in": 0, "out": 0})}
                          for z in self.lines}, **self.totals()}

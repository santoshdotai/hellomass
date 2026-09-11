"""Deterministic synthetic scene — a stand-in when no camera or footage is available.

Renders a schematic factory floor with a handful of animated "workers" that walk
through a doorway line, enter a restricted area and linger there, so every rule
in the demo can be exercised end-to-end without a camera. The exact bounding
boxes of the actors are published in `frame.metadata["gt_boxes"]`, which the
GroundTruthDetector reads; this makes the whole pipeline testable with no model.

It is clearly labelled SYNTHETIC on every frame and is never presented as real
footage."""
from __future__ import annotations

import time
from typing import Optional

import cv2
import numpy as np

from src.sources.base import Frame, SourceInfo, VideoSource


class _Actor:
    """A worker following a looping key-framed path in normalised coordinates."""

    def __init__(self, actor_id: int, waypoints: list[tuple[float, float, float]], height: float = 0.28,
                 width: float = 0.07, colour=(90, 200, 120), phase: float = 0.0, cycle: float = 30.0):
        self.id = actor_id
        self.waypoints = waypoints  # (t_seconds, x, y_feet) sorted by time; cyclic
        self.height, self.width, self.colour, self.phase, self.cycle = height, width, colour, phase, cycle

    def position(self, t: float) -> tuple[float, float] | None:
        tt = (t + self.phase) % self.cycle
        pts = self.waypoints
        for i in range(len(pts) - 1):
            t0, x0, y0 = pts[i]
            t1, x1, y1 = pts[i + 1]
            if t0 <= tt <= t1:
                if x0 is None or x1 is None:
                    return None  # off-screen segment
                a = (tt - t0) / max(t1 - t0, 1e-6)
                a = a * a * (3 - 2 * a)  # ease in/out
                return (x0 + (x1 - x0) * a, y0 + (y1 - y0) * a)
        return None


DEFAULT_ACTORS = [
    # Walks in through the doorway (x≈0.5, y≈0.85 line) into the hall and out again.
    _Actor(1, [(0, 0.52, 1.02), (4, 0.50, 0.80), (9, 0.30, 0.55), (14, 0.20, 0.45), (19, 0.35, 0.62),
               (23, 0.50, 0.82), (26, 0.52, 1.03), (30, None, None)], colour=(90, 200, 120)),
    # Enters the restricted area (top-right box) and lingers long enough for a dwell alert.
    _Actor(2, [(0, 0.55, 1.02), (5, 0.60, 0.72), (10, 0.78, 0.38), (11, 0.80, 0.36), (24, 0.82, 0.34),
               (29, 0.62, 0.70), (33, 0.55, 1.02), (40, None, None)], colour=(80, 160, 255), phase=6.0, cycle=40.0),
    # Wanders the safe walkway, never crosses the line.
    _Actor(3, [(0, 0.08, 0.40), (10, 0.30, 0.30), (20, 0.12, 0.62), (28, 0.08, 0.40)], colour=(200, 180, 90),
           phase=3.0, cycle=28.0),
    # Occasional fourth worker crossing outward.
    _Actor(4, [(0, 0.25, 0.35), (6, 0.45, 0.60), (11, 0.50, 0.85), (14, 0.51, 1.03), (60, None, None)],
           colour=(160, 120, 220), phase=20.0, cycle=60.0),
]


class SyntheticSource(VideoSource):
    kind = "synthetic"

    def __init__(self, name: str = "Synthetic Factory Floor", width: int = 960, height: int = 540, fps: float = 15.0,
                 actors: list[_Actor] | None = None, speed: float = 1.0, realtime: bool = True):
        super().__init__(name)
        self.width, self.height, self.fps = width, height, float(fps)
        self.actors = actors or DEFAULT_ACTORS
        self.speed = speed
        self.realtime = realtime
        self._t0 = 0.0
        self._background = None

    @property
    def is_live(self) -> bool:
        return True

    @property
    def masked_url(self) -> str:
        return "synthetic://factory-floor"

    def open(self) -> SourceInfo:
        self._t0 = time.monotonic()
        self._frame_index = 0
        self._background = self._draw_background()
        self.info = SourceInfo(name=self.name, kind=self.kind, masked_url=self.masked_url, width=self.width,
                               height=self.height, fps=self.fps, is_live=True, codec="synthetic",
                               extra={"synthetic": True})
        self._opened = True
        return self.info

    def _draw_background(self) -> np.ndarray:
        w, h = self.width, self.height
        img = np.full((h, w, 3), (58, 62, 66), dtype=np.uint8)
        # floor tiles
        for x in range(0, w, 60):
            cv2.line(img, (x, 0), (x, h), (66, 70, 74), 1)
        for y in range(0, h, 60):
            cv2.line(img, (0, y), (w, y), (66, 70, 74), 1)
        # machines (grey blocks) and a doorway at the bottom
        for (x1, y1, x2, y2) in [(0.05, 0.05, 0.25, 0.22), (0.30, 0.05, 0.55, 0.20), (0.05, 0.70, 0.22, 0.90)]:
            cv2.rectangle(img, (int(x1 * w), int(y1 * h)), (int(x2 * w), int(y2 * h)), (96, 100, 108), -1)
            cv2.rectangle(img, (int(x1 * w), int(y1 * h)), (int(x2 * w), int(y2 * h)), (130, 134, 140), 2)
        # hazard-striped restricted bay (top right)
        cv2.rectangle(img, (int(0.66 * w), int(0.08 * h)), (int(0.96 * w), int(0.46 * h)), (40, 44, 120), -1)
        for i in range(0, 300, 24):
            x = int(0.66 * w) + i
            cv2.line(img, (x, int(0.08 * h)), (x + 12, int(0.08 * h)), (0, 200, 255), 4)
            cv2.line(img, (x, int(0.46 * h)), (x + 12, int(0.46 * h)), (0, 200, 255), 4)
        cv2.putText(img, "RESTRICTED BAY", (int(0.68 * w), int(0.14 * h)), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (200, 220, 255), 2, cv2.LINE_AA)
        # doorway
        cv2.rectangle(img, (int(0.40 * w), int(0.93 * h)), (int(0.62 * w), h), (30, 30, 30), -1)
        cv2.putText(img, "MAIN DOOR", (int(0.43 * w), int(0.985 * h)), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (170, 170, 170), 1, cv2.LINE_AA)
        cv2.putText(img, "SYNTHETIC SCENE - not real footage", (12, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (120, 200, 255), 2, cv2.LINE_AA)
        return img

    def _draw_actor(self, img: np.ndarray, actor: _Actor, pos: tuple[float, float]) -> tuple[int, int, int, int]:
        w, h = self.width, self.height
        cx, feet = int(pos[0] * w), int(pos[1] * h)
        # perspective: further up the frame = smaller
        scale = 0.6 + 0.6 * pos[1]
        ah, aw = int(actor.height * h * scale), int(actor.width * w * scale)
        x1, y1, x2, y2 = cx - aw // 2, feet - ah, cx + aw // 2, feet
        # body + head (simple figure)
        cv2.rectangle(img, (x1 + aw // 6, y1 + ah // 4), (x2 - aw // 6, y2), actor.colour, -1)
        cv2.circle(img, (cx, y1 + ah // 8), max(4, ah // 9), (220, 200, 180), -1)
        # walking legs animation
        ph = int((time.monotonic() * 6) % 2)
        cv2.line(img, (cx - aw // 5, y2), (cx - aw // 5 - (4 if ph else -4), y2 + 6), actor.colour, 3)
        cv2.line(img, (cx + aw // 5, y2), (cx + aw // 5 + (4 if ph else -4), y2 + 6), actor.colour, 3)
        return (max(0, x1), max(0, y1), min(w - 1, x2), min(h - 1, y2))

    def read(self) -> Optional[Frame]:
        if not self._opened:
            return None
        if self.realtime:
            t = (time.monotonic() - self._t0) * self.speed
            # pace to fps
            target = self._frame_index / self.fps
            wait = target - (time.monotonic() - self._t0)
            if wait > 0:
                time.sleep(min(wait, 0.2))
        else:
            t = self._frame_index / self.fps * self.speed
        img = self._background.copy()
        boxes = []
        # draw far-away actors first for correct overlap
        placed = []
        for actor in self.actors:
            pos = actor.position(t)
            if pos is not None and -0.02 <= pos[1] <= 1.06:
                placed.append((pos[1], actor, pos))
        for _, actor, pos in sorted(placed, key=lambda p: p[0]):
            box = self._draw_actor(img, actor, pos)
            if box[3] - box[1] > 10 and box[2] - box[0] > 4 and box[1] < self.height - 2:
                boxes.append({"box": box, "actor": actor.id, "confidence": 0.93})
        cv2.putText(img, f"t={t:6.1f}s", (self.width - 130, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 180, 180),
                    1, cv2.LINE_AA)
        return self._make_frame(img, media_time=t, metadata={"gt_boxes": boxes, "synthetic": True})

    def close(self) -> None:
        self._opened = False


def default_synthetic_zones() -> list[dict]:
    """Zones that match the synthetic scene (used when a synthetic source is started with no zones saved)."""
    return [
        {"name": "Restricted Bay", "kind": "restricted", "points": [[0.66, 0.08], [0.96, 0.08], [0.96, 0.46], [0.66, 0.46]],
         "color": "#ff4d4f", "dwell_threshold_seconds": 8},
        {"name": "Assembly Hall", "kind": "occupancy", "points": [[0.05, 0.25], [0.62, 0.25], [0.62, 0.92], [0.05, 0.92]],
         "color": "#36cfc9", "occupancy_limit": 3},
        {"name": "Main Door", "kind": "line", "points": [[0.36, 0.86], [0.66, 0.86]], "color": "#ffd666",
         "direction_flipped": False},
    ]

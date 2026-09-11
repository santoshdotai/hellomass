"""Layer 4 — anonymous multi-object tracking behind a `Tracker` interface.

Track IDs are temporary and camera-local. They are re-used after a source
restart and are never linked to a person's identity or to another camera.

Backends
--------
* ByteTrackTracker – `supervision.ByteTrack` (MIT). Robust to short occlusions.
* SimpleIoUTracker – dependency-free greedy IoU/centroid matcher used for tests
                     and as a fallback when supervision is not installed."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field

import numpy as np
from loguru import logger

from src.inference.detector import Detection


@dataclass
class Track:
    track_id: int
    box: tuple[float, float, float, float]
    confidence: float
    first_seen: float
    last_seen: float
    hits: int = 1
    class_name: str = "person"
    trail: deque = field(default_factory=lambda: deque(maxlen=30))

    @property
    def label(self) -> str:
        return f"Person {self.track_id}"

    @property
    def bottom_center(self) -> tuple[float, float]:
        return ((self.box[0] + self.box[2]) / 2.0, self.box[3])

    @property
    def age_seconds(self) -> float:
        return self.last_seen - self.first_seen


class Tracker(ABC):
    backend = "base"

    def __init__(self, track_timeout_seconds: float = 2.0, min_hits: int = 2, trail_length: int = 30):
        self.track_timeout = float(track_timeout_seconds)
        self.min_hits = int(min_hits)
        self.trail_length = int(trail_length)
        self.tracks: dict[int, Track] = {}
        self.id_epoch = 0
        self.expired_last_update: list[int] = []

    @abstractmethod
    def _assign(self, detections: list[Detection], timestamp: float) -> list[tuple[int, Detection]]:
        """Return (track_id, detection) pairs for this frame."""

    def update(self, detections: list[Detection], timestamp: float) -> list[Track]:
        pairs = self._assign(detections, timestamp)
        seen = set()
        for tid, det in pairs:
            seen.add(tid)
            tr = self.tracks.get(tid)
            if tr is None:
                tr = Track(tid, det.box, det.confidence, timestamp, timestamp, 1, det.class_name,
                           deque(maxlen=self.trail_length))
                self.tracks[tid] = tr
            else:
                tr.box, tr.confidence, tr.last_seen, tr.hits = det.box, det.confidence, timestamp, tr.hits + 1
            tr.trail.append((int(tr.bottom_center[0]), int(tr.bottom_center[1])))
        # expire lost tracks (ids are remembered in `expired_last_update` so analytics can forget them)
        self.expired_last_update = [t for t, tr in self.tracks.items() if timestamp - tr.last_seen > self.track_timeout]
        for tid in self.expired_last_update:
            self.tracks.pop(tid, None)
        return [tr for tr in self.tracks.values() if tr.hits >= self.min_hits and tr.last_seen == timestamp]

    def expired_since(self, timestamp: float) -> list[int]:
        return [tid for tid, tr in self.tracks.items() if timestamp - tr.last_seen > self.track_timeout]

    def reset(self) -> None:
        self.tracks.clear()
        self.id_epoch += 1
        logger.info(f"Tracker reset (epoch {self.id_epoch}) — anonymous IDs restart")

    def info(self) -> dict:
        return {"backend": self.backend, "active_tracks": len(self.tracks), "track_timeout_seconds": self.track_timeout,
                "min_hits": self.min_hits, "id_epoch": self.id_epoch}


def iou(a, b) -> float:
    ix1, iy1, ix2, iy2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


class SimpleIoUTracker(Tracker):
    backend = "simple-iou"

    def __init__(self, track_timeout_seconds: float = 2.0, min_hits: int = 2, trail_length: int = 30,
                 iou_threshold: float = 0.3, max_center_distance_ratio: float = 0.75):
        super().__init__(track_timeout_seconds, min_hits, trail_length)
        self.iou_threshold = iou_threshold
        self.max_center_ratio = max_center_distance_ratio
        self._next_id = 1

    def reset(self) -> None:
        super().reset()
        self._next_id = 1

    def _assign(self, detections: list[Detection], timestamp: float) -> list[tuple[int, Detection]]:
        candidates = []
        for tid, tr in self.tracks.items():
            for di, det in enumerate(detections):
                score = iou(tr.box, det.box)
                if score < self.iou_threshold:
                    # allow centroid matching for fast movers / lost tracks
                    cx, cy = (tr.box[0] + tr.box[2]) / 2, (tr.box[1] + tr.box[3]) / 2
                    dx, dy = (det.box[0] + det.box[2]) / 2, (det.box[1] + det.box[3]) / 2
                    diag = max(1.0, ((tr.box[2] - tr.box[0]) ** 2 + (tr.box[3] - tr.box[1]) ** 2) ** 0.5)
                    dist = ((cx - dx) ** 2 + (cy - dy) ** 2) ** 0.5
                    if dist > diag * self.max_center_ratio:
                        continue
                    score = 0.01 + 0.2 * (1 - dist / (diag * self.max_center_ratio))
                candidates.append((score, tid, di))
        candidates.sort(reverse=True)
        used_t, used_d, pairs = set(), set(), []
        for score, tid, di in candidates:
            if tid in used_t or di in used_d:
                continue
            used_t.add(tid)
            used_d.add(di)
            pairs.append((tid, detections[di]))
        for di, det in enumerate(detections):
            if di not in used_d:
                pairs.append((self._next_id, det))
                self._next_id += 1
        return pairs


class ByteTrackTracker(Tracker):
    backend = "bytetrack"

    def __init__(self, track_timeout_seconds: float = 2.0, min_hits: int = 2, trail_length: int = 30,
                 frame_rate: float = 10.0, activation_threshold: float = 0.25, match_threshold: float = 0.8):
        super().__init__(track_timeout_seconds, min_hits, trail_length)
        import supervision as sv  # MIT
        self._sv = sv
        self.frame_rate = max(1.0, float(frame_rate))
        self._kwargs = dict(track_activation_threshold=activation_threshold,
                            lost_track_buffer=max(1, int(track_timeout_seconds * self.frame_rate)),
                            minimum_matching_threshold=match_threshold, frame_rate=int(self.frame_rate),
                            minimum_consecutive_frames=1)
        self._bt = sv.ByteTrack(**self._kwargs)

    def reset(self) -> None:
        super().reset()
        self._bt = self._sv.ByteTrack(**self._kwargs)

    def _assign(self, detections: list[Detection], timestamp: float) -> list[tuple[int, Detection]]:
        sv = self._sv
        if detections:
            xyxy = np.array([d.box for d in detections], dtype=np.float32)
            conf = np.array([d.confidence for d in detections], dtype=np.float32)
            cls = np.array([d.class_id for d in detections], dtype=int)
            dets = sv.Detections(xyxy=xyxy, confidence=conf, class_id=cls)
        else:
            dets = sv.Detections.empty()
        tracked = self._bt.update_with_detections(dets)
        pairs = []
        if tracked.tracker_id is None:
            return pairs
        for box, conf, tid in zip(tracked.xyxy, tracked.confidence, tracked.tracker_id):
            pairs.append((int(tid), Detection(tuple(float(v) for v in box), float(conf))))
        return pairs


def create_tracker(tracking_cfg: dict, analytics_fps: float = 10.0) -> Tracker:
    backend = (tracking_cfg.get("backend") or "auto").lower()
    timeout = float(tracking_cfg.get("track_timeout_seconds", 2.0))
    min_hits = int(tracking_cfg.get("min_hits", 2))
    trail = int(tracking_cfg.get("trail_length", 30))
    if backend in ("auto", "bytetrack"):
        try:
            return ByteTrackTracker(timeout, min_hits, trail, frame_rate=analytics_fps)
        except Exception as exc:
            logger.warning(f"ByteTrack unavailable ({exc}); using the simple IoU tracker")
    return SimpleIoUTracker(timeout, min_hits, trail)

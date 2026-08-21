"""Activity / motion engine (Phase 10 foundation, Phase 2.5).

V0.1 derives "is this person moving" from centroid displacement over a
rolling time window — no action-recognition model required. Pose data
(when ENABLE_POSE=true) can tighten this estimate later without changing
the interface: `ActivityEngine.update()` is the single integration point
future models plug into.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from backend.core.geometry import euclidean_distance

Point = tuple[float, float]


@dataclass
class _TrackMotionState:
    history: deque = field(default_factory=lambda: deque(maxlen=150))  # (timestamp, point)
    last_movement_time: float = 0.0
    first_seen: float = 0.0


class ActivityEngine:
    """Normalized-coordinate motion tracking. `motion_threshold` is in
    normalized units (fraction of frame width/height) — displacement below
    this over `window_seconds` is treated as "not moving"."""

    def __init__(self, motion_threshold: float = 0.015, window_seconds: float = 3.0):
        self.motion_threshold = motion_threshold
        self.window_seconds = window_seconds
        self._states: dict[int, _TrackMotionState] = {}

    def update(self, track_id: int, point: Point, timestamp: float) -> dict:
        state = self._states.get(track_id)
        if state is None:
            state = _TrackMotionState(last_movement_time=timestamp, first_seen=timestamp)
            self._states[track_id] = state

        state.history.append((timestamp, point))
        while state.history and timestamp - state.history[0][0] > self.window_seconds:
            state.history.popleft()

        displacement = 0.0
        if len(state.history) >= 2:
            oldest_point = state.history[0][1]
            displacement = euclidean_distance(oldest_point, point)

        is_moving = displacement >= self.motion_threshold
        if is_moving:
            state.last_movement_time = timestamp

        idle_duration = max(0.0, timestamp - state.last_movement_time)
        return {
            "is_moving": is_moving,
            "displacement": displacement,
            "idle_duration": idle_duration,
        }

    def idle_duration(self, track_id: int, timestamp: float) -> float:
        state = self._states.get(track_id)
        if state is None:
            return 0.0
        return max(0.0, timestamp - state.last_movement_time)

    def forget_track(self, track_id: int):
        self._states.pop(track_id, None)

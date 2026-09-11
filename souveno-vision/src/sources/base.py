"""Layer 1 — VideoSource interface and the threaded FrameGrabber.

A `VideoSource` knows how to open/read/reconnect/close one input (webcam,
file, RTSP, synthetic, future ONVIF/NVR/SDK connectors). It is deliberately
blocking and simple. The `FrameGrabber` wraps a source in a worker thread,
keeps only the *latest* frame (so latency never accumulates), detects stale
streams, drives reconnection with exponential backoff, and exposes a
connection status the dashboard can show without ever blocking on I/O."""
from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

import numpy as np
from loguru import logger


class SourceStatus(str, Enum):
    IDLE = "idle"
    CONNECTING = "connecting"
    LIVE = "live"
    DEGRADED = "degraded"
    DISCONNECTED = "disconnected"
    ENDED = "ended"
    CLOSED = "closed"
    ERROR = "error"


@dataclass
class SourceInfo:
    name: str
    kind: str
    masked_url: str = ""
    width: int = 0
    height: int = 0
    fps: float = 0.0
    total_frames: int = 0
    duration_seconds: float = 0.0
    is_live: bool = True
    codec: str = ""
    stream_profile: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["extra"] = dict(self.extra)
        return d


@dataclass
class Frame:
    image: np.ndarray
    index: int
    captured_at: float            # wall clock (time.time())
    monotonic: float              # time.monotonic() at capture
    media_time: float = 0.0       # seconds into a recorded file (0 for live)
    source_name: str = ""
    metadata: dict = field(default_factory=dict)

    @property
    def width(self) -> int:
        return int(self.image.shape[1])

    @property
    def height(self) -> int:
        return int(self.image.shape[0])


class SourceError(RuntimeError):
    """Raised with a presenter-friendly message."""


class VideoSource(ABC):
    kind: str = "base"

    def __init__(self, name: str):
        self.name = name
        self.info: Optional[SourceInfo] = None
        self._frame_index = 0
        self._opened = False

    # ---- abstract -----------------------------------------------------------------
    @abstractmethod
    def open(self) -> SourceInfo:
        """Connect and return SourceInfo. Must raise SourceError with a clear message on failure."""

    @abstractmethod
    def read(self) -> Optional[Frame]:
        """Blocking read of the next frame. None = end of stream / read failure."""

    @abstractmethod
    def close(self) -> None:
        ...

    # ---- defaults ------------------------------------------------------------------
    @property
    def masked_url(self) -> str:
        return self.info.masked_url if self.info else ""

    @property
    def is_live(self) -> bool:
        return True

    @property
    def is_open(self) -> bool:
        return self._opened

    @property
    def pace_to_fps(self) -> bool:
        """True for recorded files: the grabber replays them at their native frame rate."""
        return False

    def reconnect(self) -> SourceInfo:
        self.close()
        return self.open()

    def reset_index(self) -> None:
        self._frame_index = 0

    def _make_frame(self, image: np.ndarray, media_time: float = 0.0, metadata: dict | None = None) -> Frame:
        frame = Frame(image=image, index=self._frame_index, captured_at=time.time(),
                      monotonic=time.monotonic(), media_time=media_time, source_name=self.name,
                      metadata=metadata or {})
        self._frame_index += 1
        return frame

    def describe(self) -> dict:
        return {"name": self.name, "kind": self.kind, "masked_url": self.masked_url,
                "info": self.info.to_dict() if self.info else None}


@dataclass
class ReconnectPolicy:
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0
    multiplier: float = 2.0
    stale_after_seconds: float = 3.0
    disconnected_after_seconds: float = 8.0
    max_attempts: int = 0  # 0 = forever


class FrameGrabber:
    """Worker thread around a VideoSource with a latest-frame (size 1) buffer."""

    def __init__(self, source: VideoSource, policy: ReconnectPolicy | None = None,
                 on_status: Callable[[SourceStatus, SourceStatus, VideoSource], None] | None = None,
                 pace_files: bool = True):
        self.source = source
        self.policy = policy or ReconnectPolicy()
        self.on_status = on_status
        self.pace_files = pace_files
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._latest: Optional[Frame] = None
        self._consumed = True
        self._status = SourceStatus.IDLE
        self._last_frame_monotonic = 0.0
        self._last_error = ""
        self.frames_captured = 0
        self.frames_dropped = 0
        self.reconnect_count = 0
        self.connect_attempts = 0
        self.started_at = 0.0
        self.last_frame_wall = 0.0
        self.ended = False

    # ---- lifecycle -------------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self.ended = False
        self.started_at = time.time()
        self._thread = threading.Thread(target=self._run, name=f"grabber-{self.source.name}", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        with self._cond:
            self._cond.notify_all()
        if self._thread and self._thread.is_alive() and threading.current_thread() is not self._thread:
            self._thread.join(timeout=timeout)
        try:
            self.source.close()
        except Exception as exc:  # pragma: no cover
            logger.debug(f"Source close error: {exc}")
        self._set_status(SourceStatus.CLOSED)

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # ---- status ------------------------------------------------------------------
    @property
    def status(self) -> SourceStatus:
        with self._lock:
            status = self._status
            age = time.monotonic() - self._last_frame_monotonic if self._last_frame_monotonic else None
        if status == SourceStatus.LIVE and age is not None and self.source.is_live:
            if age > self.policy.disconnected_after_seconds:
                return SourceStatus.DISCONNECTED
            if age > self.policy.stale_after_seconds:
                return SourceStatus.DEGRADED
        return status

    @property
    def last_error(self) -> str:
        return self._last_error

    def frame_age_seconds(self) -> Optional[float]:
        with self._lock:
            if not self._last_frame_monotonic:
                return None
            return time.monotonic() - self._last_frame_monotonic

    def _set_status(self, new: SourceStatus) -> None:
        with self._lock:
            old = self._status
            self._status = new
            if new == SourceStatus.LIVE and old != SourceStatus.LIVE:
                self._last_frame_monotonic = time.monotonic()  # stale timer starts now, even if no frame ever arrives
        if old != new:
            logger.info(f"Source '{self.source.name}' status {old.value} -> {new.value}")
            if self.on_status:
                try:
                    self.on_status(old, new, self.source)
                except Exception:  # pragma: no cover
                    logger.exception("on_status callback failed")

    # ---- frames ------------------------------------------------------------------
    def latest(self, timeout: float = 0.0, only_new: bool = True) -> Optional[Frame]:
        """Return the newest frame. With only_new=True a frame is handed out once."""
        with self._cond:
            if only_new and self._consumed and timeout > 0:
                self._cond.wait(timeout=timeout)
            if self._latest is None or (only_new and self._consumed):
                return None
            self._consumed = True
            return self._latest

    def peek(self) -> Optional[Frame]:
        with self._lock:
            return self._latest

    def _publish(self, frame: Frame) -> None:
        with self._cond:
            if not self._consumed:
                self.frames_dropped += 1  # consumer was slower than capture: we keep only the latest
            self._latest = frame
            self._consumed = False
            self._last_frame_monotonic = frame.monotonic
            self.last_frame_wall = frame.captured_at
            self.frames_captured += 1
            self._cond.notify_all()

    # ---- worker ------------------------------------------------------------------
    def _open_with_backoff(self) -> bool:
        delay = self.policy.initial_delay_seconds
        attempt = 0
        while not self._stop.is_set():
            attempt += 1
            self.connect_attempts += 1
            self._set_status(SourceStatus.CONNECTING)
            try:
                if self.source.is_open:
                    self.source.reconnect()
                else:
                    self.source.open()
                self._last_error = ""
                return True
            except Exception as exc:
                self._last_error = str(exc)
                logger.warning(f"Source '{self.source.name}' connect attempt {attempt} failed: {exc}")
                self._set_status(SourceStatus.DISCONNECTED)
                if self.policy.max_attempts and attempt >= self.policy.max_attempts:
                    self._set_status(SourceStatus.ERROR)
                    return False
                if self._stop.wait(delay):
                    return False
                delay = min(delay * self.policy.multiplier, self.policy.max_delay_seconds)
        return False

    def _run(self) -> None:
        if not self.source.is_open and not self._open_with_backoff():
            return
        self._set_status(SourceStatus.LIVE)
        consecutive_failures = 0
        fps = (self.source.info.fps if self.source.info and self.source.info.fps else 25.0)
        frame_interval = 1.0 / max(fps, 1.0)
        next_deadline = time.monotonic()
        while not self._stop.is_set():
            try:
                frame = self.source.read()
            except Exception as exc:
                self._last_error = str(exc)
                logger.warning(f"Source '{self.source.name}' read error: {exc}")
                frame = None
            if frame is None:
                if not self.source.is_live:
                    # finite file that is not looping
                    self.ended = True
                    self._set_status(SourceStatus.ENDED)
                    return
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    self._set_status(SourceStatus.DISCONNECTED)
                    self.reconnect_count += 1
                    if not self._open_with_backoff():
                        return
                    self._set_status(SourceStatus.LIVE)
                    consecutive_failures = 0
                    fps = (self.source.info.fps if self.source.info and self.source.info.fps else fps)
                    frame_interval = 1.0 / max(fps, 1.0)
                else:
                    self._stop.wait(0.05)
                continue
            consecutive_failures = 0
            if self.status != SourceStatus.LIVE and self._status in (SourceStatus.LIVE, SourceStatus.DISCONNECTED):
                # frames flowing again after a stale period
                self._set_status(SourceStatus.LIVE)
            self._publish(frame)
            if self.pace_files and self.source.pace_to_fps:
                next_deadline += frame_interval
                sleep_for = next_deadline - time.monotonic()
                if sleep_for > 0:
                    self._stop.wait(sleep_for)
                elif sleep_for < -1.0:
                    next_deadline = time.monotonic()

    def stats(self) -> dict:
        return {
            "status": self.status.value,
            "frames_captured": self.frames_captured,
            "frames_dropped": self.frames_dropped,
            "reconnect_count": self.reconnect_count,
            "connect_attempts": self.connect_attempts,
            "last_frame_at": self.last_frame_wall or None,
            "frame_age_seconds": self.frame_age_seconds(),
            "last_error": self._last_error,
            "source": self.source.describe(),
        }

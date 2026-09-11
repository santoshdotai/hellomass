"""Layer 7 — evidence: annotated snapshots, a circular pre-event frame buffer,
short before/after clips written in a background thread, storage limits and
retention clean-up. Never a continuous recording of the camera."""
from __future__ import annotations

import shutil
import threading
import time
from collections import deque
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from loguru import logger

from src.inference.preprocess import resize_max_width
from src.security.redaction import safe_filename
from src.utils.time_utils import utc_iso


class PreEventBuffer:
    """Keeps the last N seconds of (timestamp, frame) at analytics rate."""

    def __init__(self, seconds: float, fps: float, max_width: int = 960):
        self.seconds = float(seconds)
        self.fps = max(1.0, float(fps))
        self.max_width = max_width
        self._buf: deque = deque(maxlen=max(2, int(self.seconds * self.fps) + 1))
        self._lock = threading.Lock()

    def push(self, frame: np.ndarray, timestamp: float) -> None:
        small, _ = resize_max_width(frame, self.max_width)
        with self._lock:
            self._buf.append((timestamp, small))

    def snapshot(self) -> list[tuple[float, np.ndarray]]:
        with self._lock:
            return list(self._buf)

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()


class ClipRecorder:
    """Collects pre-event frames plus `post_seconds` of live frames, then encodes in a worker thread."""

    def __init__(self, event_id: str, out_path: Path, pre_frames: list[tuple[float, np.ndarray]], post_seconds: float,
                 fps: float, on_done=None):
        self.event_id = event_id
        self.out_path = out_path
        self.frames = list(pre_frames)
        self.post_seconds = float(post_seconds)
        self.fps = max(1.0, float(fps))
        self.started = time.time()
        self.done = False
        self.result: Optional[str] = None
        self._on_done = on_done
        self._lock = threading.Lock()

    def push(self, frame: np.ndarray, timestamp: float, max_width: int) -> bool:
        """Returns True when the recorder has collected everything it needs."""
        with self._lock:
            if self.done:
                return True
            small, _ = resize_max_width(frame, max_width)
            self.frames.append((timestamp, small))
            if time.time() - self.started >= self.post_seconds:
                threading.Thread(target=self._encode, name=f"clip-{self.event_id}", daemon=True).start()
                self.done = True
                return True
        return False

    def _encode(self) -> None:
        try:
            if not self.frames:
                return
            h, w = self.frames[0][1].shape[:2]
            self.out_path.parent.mkdir(parents=True, exist_ok=True)
            writer = cv2.VideoWriter(str(self.out_path), cv2.VideoWriter_fourcc(*"mp4v"), self.fps, (w, h))
            path = self.out_path
            if not writer.isOpened():  # codec missing: fall back to Motion-JPEG AVI (always available)
                path = self.out_path.with_suffix(".avi")
                writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), self.fps, (w, h))
            for _, fr in self.frames:
                if fr.shape[0] != h or fr.shape[1] != w:
                    fr = cv2.resize(fr, (w, h))
                writer.write(fr)
            writer.release()
            self.result = str(path)
            logger.info(f"Evidence clip saved {path.name} ({len(self.frames)} frames)")
        except Exception:
            logger.exception("Clip encoding failed")
        finally:
            self.frames = []
            if self._on_done:
                self._on_done(self.event_id, self.result)


class EvidenceManager:
    def __init__(self, directory: Path, pre_seconds: float = 4, post_seconds: float = 4, fps: float = 8,
                 clip_enabled: bool = True, max_concurrent_clips: int = 2, max_clips_per_minute: int = 6,
                 retention_days: int = 14, max_storage_mb: int = 2048, max_width: int = 1280):
        self.dir = Path(directory)
        self.snapshots_dir = self.dir / "snapshots"
        self.clips_dir = self.dir / "clips"
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.clips_dir.mkdir(parents=True, exist_ok=True)
        self.pre_seconds, self.post_seconds, self.fps = float(pre_seconds), float(post_seconds), float(fps)
        self.clip_enabled = clip_enabled
        self.max_concurrent = int(max_concurrent_clips)
        self.max_per_minute = int(max_clips_per_minute)
        self.retention_days = int(retention_days)
        self.max_storage_mb = int(max_storage_mb)
        self.max_width = int(max_width)
        self.buffer = PreEventBuffer(pre_seconds, fps, min(max_width, 960))
        self._recorders: list[ClipRecorder] = []
        self._clip_times: deque = deque(maxlen=100)
        self._lock = threading.Lock()
        self.on_clip_done = None  # callable(event_id, path)
        self.clips_skipped = 0
        self.last_cleanup = 0.0

    # ---- per-frame ------------------------------------------------------------------
    def push_frame(self, frame: np.ndarray, timestamp: float) -> None:
        self.buffer.push(frame, timestamp)
        with self._lock:
            active = list(self._recorders)
        finished = [r for r in active if r.push(frame, timestamp, min(self.max_width, 960))]
        if finished:
            with self._lock:
                self._recorders = [r for r in self._recorders if r not in finished]

    # ---- evidence creation ------------------------------------------------------------
    def save_snapshot(self, event_id: str, event_type: str, frame: np.ndarray, caption: str = "") -> Optional[str]:
        try:
            img, _ = resize_max_width(frame, self.max_width)
            img = img.copy()
            h, w = img.shape[:2]
            cv2.rectangle(img, (0, h - 30), (w, h), (20, 20, 20), -1)
            text = f"SOUVENO AI | {event_type} | {utc_iso()} | {caption}"[:120]
            cv2.putText(img, text, (8, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (230, 230, 230), 1, cv2.LINE_AA)
            name = safe_filename(f"{event_id}_{event_type}") + ".jpg"
            path = self.snapshots_dir / name
            cv2.imwrite(str(path), img, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            return str(path)
        except Exception:
            logger.exception("Snapshot save failed")
            return None

    def request_clip(self, event_id: str, event_type: str) -> bool:
        if not self.clip_enabled:
            return False
        now = time.time()
        with self._lock:
            recent = [t for t in self._clip_times if now - t < 60]
            if len(self._recorders) >= self.max_concurrent or len(recent) >= self.max_per_minute:
                self.clips_skipped += 1
                logger.info(f"Clip skipped for {event_id} (rate limit: {len(self._recorders)} active, {len(recent)}/min)")
                return False
            self._clip_times.append(now)
            name = safe_filename(f"{event_id}_{event_type}") + ".mp4"
            rec = ClipRecorder(event_id, self.clips_dir / name, self.buffer.snapshot(), self.post_seconds, self.fps,
                               on_done=self._clip_done)
            self._recorders.append(rec)
        return True

    def _clip_done(self, event_id: str, path: Optional[str]) -> None:
        if self.on_clip_done and path:
            try:
                self.on_clip_done(event_id, path)
            except Exception:
                logger.exception("on_clip_done failed")

    # ---- housekeeping -----------------------------------------------------------------
    def storage_mb(self) -> float:
        total = 0
        for d in (self.snapshots_dir, self.clips_dir):
            for f in d.glob("*"):
                if f.is_file():
                    total += f.stat().st_size
        return total / 1e6

    def cleanup(self) -> dict:
        """Delete evidence older than retention_days, then oldest-first until under max_storage_mb."""
        removed = 0
        cutoff = time.time() - self.retention_days * 86400
        files = [f for d in (self.snapshots_dir, self.clips_dir) for f in d.glob("*") if f.is_file() and f.suffix != ".gitkeep"]
        for f in files:
            if f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
                removed += 1
        files = sorted((f for f in files if f.exists()), key=lambda f: f.stat().st_mtime)
        total = sum(f.stat().st_size for f in files)
        while files and total > self.max_storage_mb * 1e6:
            f = files.pop(0)
            total -= f.stat().st_size
            f.unlink(missing_ok=True)
            removed += 1
        self.last_cleanup = time.time()
        free_mb = shutil.disk_usage(self.dir).free / 1e6
        if removed:
            logger.info(f"Evidence cleanup removed {removed} file(s); {total / 1e6:.1f} MB kept, {free_mb:.0f} MB free")
        return {"removed": removed, "storage_mb": round(total / 1e6, 1), "disk_free_mb": round(free_mb, 1)}

    def status(self) -> dict:
        with self._lock:
            active = len(self._recorders)
        return {"active_clip_recorders": active, "clips_skipped": self.clips_skipped, "storage_mb": round(self.storage_mb(), 1),
                "retention_days": self.retention_days, "max_storage_mb": self.max_storage_mb, "clip_enabled": self.clip_enabled,
                "pre_seconds": self.pre_seconds, "post_seconds": self.post_seconds}

"""Layer 11 — HealthMonitor: FPS counters, latency, drops, reconnects, last
frame time, component status, disk space, CPU/GPU mode."""
from __future__ import annotations

import platform
import shutil
import threading
import time
from collections import deque
from pathlib import Path

from src.utils.time_utils import utc_iso


class _RateMeter:
    def __init__(self, window_seconds: float = 5.0):
        self.window = window_seconds
        self._times: deque = deque()

    def tick(self, t: float | None = None) -> None:
        t = t or time.monotonic()
        self._times.append(t)
        cutoff = t - self.window
        while self._times and self._times[0] < cutoff:
            self._times.popleft()

    def rate(self) -> float:
        if len(self._times) < 2:
            return 0.0
        span = self._times[-1] - self._times[0]
        return (len(self._times) - 1) / span if span > 0 else 0.0


class HealthMonitor:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self._lock = threading.Lock()
        self.capture = _RateMeter()
        self.inference = _RateMeter()
        self.latencies: deque = deque(maxlen=120)
        self.dropped_frames = 0
        self.skipped_frames = 0
        self.reconnects = 0
        self.last_frame_at: float | None = None
        self.components: dict[str, dict] = {}
        self.started_at = time.time()
        self.errors: deque = deque(maxlen=20)
        self.last_persist = 0.0

    def record_capture(self) -> None:
        with self._lock:
            self.capture.tick()
            self.last_frame_at = time.time()

    def record_inference(self, latency_ms: float) -> None:
        with self._lock:
            self.inference.tick()
            self.latencies.append(latency_ms)

    def record_dropped(self, n: int = 1) -> None:
        with self._lock:
            self.dropped_frames += n

    def record_skipped(self, n: int = 1) -> None:
        with self._lock:
            self.skipped_frames += n

    def record_reconnect(self) -> None:
        with self._lock:
            self.reconnects += 1

    def record_error(self, component: str, message: str) -> None:
        with self._lock:
            self.errors.appendleft({"at": utc_iso(), "component": component, "message": message[:300]})

    def set_component(self, name: str, ok: bool, detail: str = "", **extra) -> None:
        with self._lock:
            self.components[name] = {"ok": bool(ok), "detail": detail, "updated_at": utc_iso(), **extra}

    def system(self) -> dict:
        info = {"platform": f"{platform.system()} {platform.release()}", "python": platform.python_version(),
                "cpu_percent": None, "memory_percent": None, "disk_free_mb": None, "disk_total_mb": None}
        try:
            import psutil
            info["cpu_percent"] = psutil.cpu_percent(interval=None)
            info["memory_percent"] = psutil.virtual_memory().percent
        except Exception:
            pass
        try:
            target = self.data_dir if self.data_dir.exists() else Path.cwd()
            usage = shutil.disk_usage(target)
            info["disk_free_mb"] = round(usage.free / 1e6)
            info["disk_total_mb"] = round(usage.total / 1e6)
        except Exception:
            pass
        return info

    def snapshot(self) -> dict:
        with self._lock:
            lat = list(self.latencies)
            snap = {
                "uptime_seconds": round(time.time() - self.started_at),
                "capture_fps": round(self.capture.rate(), 1),
                "inference_fps": round(self.inference.rate(), 1),
                "latency_ms": round(sum(lat) / len(lat), 1) if lat else 0.0,
                "latency_p95_ms": round(sorted(lat)[int(len(lat) * 0.95) - 1], 1) if len(lat) >= 5 else (round(max(lat), 1) if lat else 0.0),
                "dropped_frames": self.dropped_frames,
                "skipped_frames": self.skipped_frames,
                "reconnects": self.reconnects,
                "last_frame_at": utc_iso_from_ts(self.last_frame_at) if self.last_frame_at else None,
                "seconds_since_last_frame": round(time.time() - self.last_frame_at, 1) if self.last_frame_at else None,
                "components": dict(self.components),
                "recent_errors": list(self.errors),
            }
        snap["system"] = self.system()
        return snap


def utc_iso_from_ts(ts: float) -> str:
    from datetime import datetime, timezone
    return utc_iso(datetime.fromtimestamp(ts, tz=timezone.utc))

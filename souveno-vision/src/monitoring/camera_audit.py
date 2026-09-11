"""Layer 13 — camera / source compatibility audit.

Probes ONE user-supplied source for a few seconds and classifies it:
    A  AI ready                      B  Usable after configuration
    C  Basic analytics only          D  Unsuitable for the requested use case
No network scanning — only the URL/index/file the operator typed is tested."""
from __future__ import annotations

import statistics
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict

from loguru import logger

from src.sources.base import SourceError
from src.sources.factory import create_source


@dataclass
class AuditReport:
    audit_id: str
    source_name: str
    source_kind: str
    masked_url: str
    stream_profile: str = ""
    reachable: bool = False
    connect_time_ms: float | None = None
    resolution: str = ""
    reported_fps: float | None = None
    observed_fps: float | None = None
    codec: str = ""
    frames_read: int = 0
    duration_seconds: float = 0.0
    mean_frame_interval_ms: float | None = None
    frame_interval_std_ms: float | None = None
    max_gap_ms: float | None = None
    stale_events: int = 0
    read_failures: int = 0
    frame_stability: str = ""
    classification: str = ""
    classification_label: str = ""
    notes: list[str] = field(default_factory=list)
    error: str = ""
    status: str = "running"
    finished_at: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


CLASS_LABELS = {"A": "AI ready", "B": "Usable after configuration", "C": "Basic analytics only",
                "D": "Unsuitable for requested use case"}


def _classify(r: AuditReport) -> None:
    notes = r.notes
    if not r.reachable or r.frames_read < 3:
        r.classification = "D"
        notes.append("Source not reachable or no frames decoded — check URL/credentials/codec before any analytics.")
    else:
        w, h = (int(v) for v in r.resolution.split("x")) if "x" in r.resolution else (0, 0)
        fps = r.observed_fps or 0.0
        score = 0
        if w >= 1280 and h >= 720:
            score += 2
        elif w >= 640 and h >= 360:
            score += 1
            notes.append("Resolution below 720p: fine for counting/intrusion, small/distant people may be missed.")
        else:
            notes.append("Very low resolution: only coarse presence detection is realistic.")
        if fps >= 10:
            score += 2
        elif fps >= 5:
            score += 1
            notes.append("Observed FPS between 5 and 10: tracking works but fast movement may break track continuity.")
        else:
            notes.append("Observed FPS below 5: line crossing and tracking will be unreliable.")
        if r.frame_stability == "stable":
            score += 2
        elif r.frame_stability == "jittery":
            score += 1
            notes.append("Irregular frame delivery: prefer TCP transport, a wired link, or the substream.")
        else:
            notes.append("Stalls/stale frames observed: network or camera CPU load — use the substream and check VLAN routing.")
        if r.read_failures:
            notes.append(f"{r.read_failures} read failure(s) during the probe.")
        if r.codec.upper().startswith(("HEVC", "H265", "HVC1", "HEV1")):
            notes.append("H.265/HEVC stream: works here but costs more CPU; many edge tools prefer H.264 for the analytics substream.")
        if score >= 6:
            r.classification = "A"
        elif score >= 4:
            r.classification = "B"
            notes.append("Usable after adjusting stream settings (substream, FPS, resolution, TCP transport).")
        elif score >= 2:
            r.classification = "C"
        else:
            r.classification = "D"
    r.classification_label = CLASS_LABELS[r.classification]
    if r.source_kind == "rtsp" and r.stream_profile:
        notes.append(f"Tested the {r.stream_profile}-stream. Substreams (640x360–1280x720 @ 8–15 fps) are usually the right choice for analytics.")


def run_audit(spec: dict, duration_seconds: float = 8.0, rtsp_env: dict | None = None, base_dir=None) -> AuditReport:
    audit_id = f"AUD-{uuid.uuid4().hex[:6].upper()}"
    name = spec.get("name") or spec.get("type", "source")
    report = AuditReport(audit_id=audit_id, source_name=name, source_kind=spec.get("type", ""), masked_url="",
                         stream_profile=spec.get("stream_profile", ""))
    source = None
    try:
        source = create_source(spec, base_dir=base_dir, rtsp_env=rtsp_env)
        report.masked_url = source.masked_url
        t0 = time.perf_counter()
        info = source.open()
        report.connect_time_ms = round((time.perf_counter() - t0) * 1000, 1)
        report.reachable = True
        report.resolution = f"{info.width}x{info.height}"
        report.reported_fps = round(info.fps, 1) if info.fps else None
        report.codec = info.codec or ""
        intervals: list[float] = []
        last = time.perf_counter()
        start = last
        while time.perf_counter() - start < duration_seconds:
            fr = source.read()
            now = time.perf_counter()
            if fr is None:
                report.read_failures += 1
                if report.read_failures > 10:
                    break
                time.sleep(0.05)
                continue
            gap = (now - last) * 1000
            last = now
            intervals.append(gap)
            report.frames_read += 1
            if gap > 1500:
                report.stale_events += 1
        report.duration_seconds = round(time.perf_counter() - start, 1)
        if len(intervals) >= 2:
            body = intervals[1:]
            report.mean_frame_interval_ms = round(statistics.mean(body), 1)
            report.frame_interval_std_ms = round(statistics.pstdev(body), 1) if len(body) > 1 else 0.0
            report.max_gap_ms = round(max(body), 1)
            report.observed_fps = round(1000.0 / report.mean_frame_interval_ms, 1) if report.mean_frame_interval_ms else None
            cv = (report.frame_interval_std_ms / report.mean_frame_interval_ms) if report.mean_frame_interval_ms else 1.0
            report.frame_stability = "stable" if (cv < 0.5 and report.stale_events == 0) else ("jittery" if report.stale_events == 0 else "stalling")
        else:
            report.frame_stability = "no-frames"
    except SourceError as exc:
        report.error = str(exc)
        report.notes.append(str(exc))
    except Exception as exc:  # pragma: no cover
        report.error = f"{type(exc).__name__}: {exc}"
        logger.exception("Audit failed")
    finally:
        if source is not None:
            try:
                source.close()
            except Exception:
                pass
    _classify(report)
    report.status = "done"
    report.finished_at = time.time()
    logger.info(f"Camera audit {audit_id} for {report.masked_url or name}: class {report.classification} "
                f"({report.resolution} @ {report.observed_fps} fps)")
    return report


class AuditRunner:
    """Runs audits on background threads so the UI never blocks."""

    def __init__(self, rtsp_env: dict | None = None, base_dir=None):
        self.rtsp_env = rtsp_env
        self.base_dir = base_dir
        self.reports: dict[str, AuditReport] = {}
        self._lock = threading.Lock()

    def start(self, spec: dict, duration_seconds: float = 8.0) -> str:
        audit_id = f"AUD-{uuid.uuid4().hex[:6].upper()}"
        placeholder = AuditReport(audit_id=audit_id, source_name=spec.get("name") or spec.get("type", "source"),
                                  source_kind=spec.get("type", ""), masked_url="", status="running")
        with self._lock:
            self.reports[audit_id] = placeholder

        def _work():
            report = run_audit(spec, duration_seconds, self.rtsp_env, self.base_dir)
            report.audit_id = audit_id
            with self._lock:
                self.reports[audit_id] = report

        threading.Thread(target=_work, name=f"audit-{audit_id}", daemon=True).start()
        return audit_id

    def get(self, audit_id: str) -> AuditReport | None:
        with self._lock:
            return self.reports.get(audit_id)

    def list(self) -> list[dict]:
        with self._lock:
            return [r.to_dict() for r in sorted(self.reports.values(), key=lambda r: r.finished_at or time.time(), reverse=True)]

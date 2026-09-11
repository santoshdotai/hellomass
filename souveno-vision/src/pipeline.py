"""VisionPipeline — the orchestrator that connects every layer:

  VideoSource -> FrameGrabber(thread) -> [processing thread] resize -> Detector -> Tracker
      -> SpatialAnalytics -> RulesEngine -> EventService (+ EvidenceManager, WebhookDispatcher)
      -> overlay -> latest JPEG / state for the dashboard

Capture and processing run on their own threads; the web server only ever
reads the latest state, so a frozen camera can never freeze the UI."""
from __future__ import annotations

import hashlib
import threading
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from loguru import logger

from src.analytics.spatial import FrameAnalytics, SpatialAnalytics
from src.analytics.zones import Zone, validate_zones
from src.events.evidence import EvidenceManager
from src.events.service import EventService
from src.events.webhook import WebhookDispatcher
from src.inference.detector import Detector, create_detector
from src.inference.preprocess import resize_max_width
from src.monitoring.health import HealthMonitor
from src.rules.engine import RulesEngine
from src.rules.models import EventCandidate, Rule, RuleType, Severity, default_rules
from src.security.redaction import redact_mapping, safe_filename
from src.sources.base import FrameGrabber, ReconnectPolicy, SourceError, SourceStatus, VideoSource
from src.sources.factory import create_source
from src.sources.synthetic import default_synthetic_zones
from src.storage.repositories import Repositories
from src.tracking.tracker import Tracker, create_tracker
from src.ui.overlay import draw_message, draw_status_strip, draw_tracks, draw_zones, placeholder_frame
from src.utils.config import Config, resolve_path
from src.utils.time_utils import local_display, now_utc


def source_id_for(spec: dict, source: VideoSource) -> str:
    kind = (spec.get("type") or source.kind).lower()
    if kind == "webcam":
        return f"webcam-{spec.get('index', spec.get('webcam_index', 0))}"
    if kind == "file":
        return f"file-{safe_filename(Path(spec.get('path') or spec.get('video_path') or source.name).stem)}"
    if kind == "rtsp":
        return f"rtsp-{hashlib.sha1(source.masked_url.encode()).hexdigest()[:8]}"
    return "synthetic-demo"


class VisionPipeline:
    def __init__(self, cfg: Config, repos: Repositories, events: EventService, evidence: EvidenceManager,
                 health: HealthMonitor, webhook: WebhookDispatcher | None = None, base_dir: Path | None = None,
                 clock: str = "wall"):
        self.cfg = cfg
        self.repos = repos
        self.events = events
        self.evidence = evidence
        self.health = health
        self.webhook = webhook
        self.base_dir = base_dir or Path.cwd()
        self.clock = clock  # "wall" | "media" (deterministic tests)
        self.demo_mode = bool(cfg.app.get("demo_mode", True))

        # runtime settings (config defaults + persisted overrides)
        self.settings: dict = self._initial_settings()

        self.detector: Optional[Detector] = None
        self.tracker: Optional[Tracker] = None
        self.spatial: Optional[SpatialAnalytics] = None
        self.rules_engine = RulesEngine(self._load_rules(), self.settings["business_hours"], cfg.app.get("timezone", "local"))

        self.source: Optional[VideoSource] = None
        self.grabber: Optional[FrameGrabber] = None
        self.source_id: str = ""
        self.source_spec: dict = {}
        self.zones: list[Zone] = []

        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._latest_jpeg: bytes = b""
        self._latest_raw: Optional[np.ndarray] = None
        self._latest_fa: Optional[FrameAnalytics] = None
        self._state: dict = {}
        self.paused = False
        self.last_error = ""
        self.started_at: float | None = None
        self._maintenance = threading.Thread(target=self._maintenance_loop, name="maintenance", daemon=True)
        self._maintenance_stop = threading.Event()
        self._maintenance.start()
        self._dwell_override_until = 0.0
        self._dwell_override_prev: float | None = None

    # ------------------------------------------------------------------ settings
    def _initial_settings(self) -> dict:
        c = self.cfg
        s = {
            "confidence": float(c.model.confidence),
            "analytics_fps": float(c.processing.analytics_fps),
            "device": str(c.model.device),
            "model_backend": str(c.model.backend),
            "image_size": int(c.model.image_size),
            "trail_enabled": bool(c.tracking.trail_enabled),
            "business_hours": c.business_hours.to_dict(),
            "dwell_threshold_seconds": float(c.rules.dwell_time_exceeded.get("threshold_seconds", 30)),
            "occupancy_threshold": int(c.rules.occupancy_threshold.get("threshold", 5)),
            "retention_days": int(c.evidence.retention_days),
            "clip_enabled": bool(c.evidence.clip_enabled),
            "webhook": {"enabled": bool(c.webhook.enabled), "url": str(c.webhook.url or ""),
                        "timeout_seconds": float(c.webhook.timeout_seconds), "max_retries": int(c.webhook.max_retries),
                        "backoff_seconds": float(c.webhook.backoff_seconds)},
        }
        persisted = self.repos.settings.get("runtime", {}) or {}
        for k, v in persisted.items():
            if k in s:
                s[k] = v
        return s

    def apply_settings(self, updates: dict, persist: bool = True) -> dict:
        updates = {k: v for k, v in updates.items() if k in self.settings}
        rebuild_detector = False
        for k, v in updates.items():
            if k in ("device", "model_backend", "image_size") and v != self.settings.get(k):
                rebuild_detector = True
            self.settings[k] = v
        if "confidence" in updates and self.detector:
            self.detector.confidence = float(updates["confidence"])
        if "business_hours" in updates:
            self.rules_engine.set_business_hours(self.settings["business_hours"])
        if "dwell_threshold_seconds" in updates or "occupancy_threshold" in updates:
            self._sync_rule_thresholds()
        if "retention_days" in updates:
            self.evidence.retention_days = int(updates["retention_days"])
        if "clip_enabled" in updates:
            self.evidence.clip_enabled = bool(updates["clip_enabled"])
        if "webhook" in updates and self.webhook is not None:
            w = self.settings["webhook"]
            self.webhook.configure(w.get("enabled", False), w.get("url", ""), w.get("timeout_seconds"),
                                   w.get("max_retries"), w.get("backoff_seconds"))
        if rebuild_detector:
            self.detector = None  # lazily rebuilt by the processing thread
        if persist:
            self.repos.settings.set("runtime", redact_mapping(self.settings))
        return dict(self.settings)

    def _sync_rule_thresholds(self) -> None:
        for r in self.rules_engine.rules:
            if r.rule_type == RuleType.DWELL_TIME_EXCEEDED:
                r.threshold = float(self.settings["dwell_threshold_seconds"])
            elif r.rule_type == RuleType.OCCUPANCY_THRESHOLD:
                r.threshold = int(self.settings["occupancy_threshold"])
        if self.spatial:
            self.spatial.dwell.set_default_threshold(float(self.settings["dwell_threshold_seconds"]))
        self.repos.rules.upsert_many([r.to_dict() for r in self.rules_engine.rules])

    # ------------------------------------------------------------------ rules
    def _load_rules(self) -> list[Rule]:
        stored = self.repos.rules.list()
        rules = [Rule.from_dict(r) for r in stored] if stored else default_rules(self.cfg.rules.to_dict())
        by_type = {r.rule_type for r in rules}
        for r in default_rules(self.cfg.rules.to_dict()):
            if r.rule_type not in by_type:
                rules.append(r)
        for r in rules:
            if r.rule_type == RuleType.DWELL_TIME_EXCEEDED:
                r.threshold = float(self.settings["dwell_threshold_seconds"])
            elif r.rule_type == RuleType.OCCUPANCY_THRESHOLD:
                r.threshold = int(self.settings["occupancy_threshold"])
        if not stored:
            self.repos.rules.upsert_many([r.to_dict() for r in rules])
        return rules

    def update_rules(self, rule_dicts: list[dict]) -> list[dict]:
        current = {r.rule_id: r for r in self.rules_engine.rules}
        for d in rule_dicts:
            r = current.get(d.get("rule_id"))
            if not r:
                continue
            for k in ("enabled", "severity", "cooldown_seconds", "evidence_required", "notify", "threshold", "zone_id", "source_id", "name"):
                if k in d:
                    setattr(r, k, d[k])
            if "schedule" in d and isinstance(d["schedule"], dict):
                from src.rules.models import Schedule
                r.schedule = Schedule(**{k: v for k, v in d["schedule"].items() if k in Schedule.__dataclass_fields__})
            r.severity = Severity(r.severity)
            if r.rule_type == RuleType.DWELL_TIME_EXCEEDED and r.threshold:
                self.settings["dwell_threshold_seconds"] = float(r.threshold)
                if self.spatial:
                    self.spatial.dwell.set_default_threshold(float(r.threshold))
            if r.rule_type == RuleType.OCCUPANCY_THRESHOLD and r.threshold:
                self.settings["occupancy_threshold"] = int(r.threshold)
        self.repos.rules.upsert_many([r.to_dict() for r in self.rules_engine.rules])
        self.repos.settings.set("runtime", redact_mapping(self.settings))
        return [r.to_dict() for r in self.rules_engine.rules]

    # ------------------------------------------------------------------ zones
    def load_zones(self, source_id: str, allow_default: bool = True) -> list[Zone]:
        rows = self.repos.zones.list_for_source(source_id)
        zones = [Zone.from_dict(r) for r in rows]
        if not zones and allow_default and source_id == "synthetic-demo":
            zones = [Zone.from_dict(z) for z in default_synthetic_zones()]
            self.repos.zones.replace_for_source(source_id, [z.to_dict() for z in zones])
        return zones

    def save_zones(self, source_id: str, zone_dicts: list[dict]) -> tuple[list[dict], dict]:
        zones = [Zone.from_dict(z) for z in zone_dicts]
        problems = validate_zones(zones, float(self.cfg.analytics.min_polygon_area))
        if problems:
            return [z.to_dict() for z in zones], problems
        saved = self.repos.zones.replace_for_source(source_id, [z.to_dict() for z in zones])
        if source_id == self.source_id:
            self.set_zones([Zone.from_dict(z) for z in saved])
        return saved, {}

    def set_zones(self, zones: list[Zone]) -> None:
        with self._lock:
            self.zones = zones
            self.spatial = SpatialAnalytics(zones, self.cfg.analytics.to_dict(), float(self.settings["dwell_threshold_seconds"]))
        self.rules_engine.reset_cooldowns()
        logger.info(f"Zones applied to '{self.source_id}': {[z.name for z in zones]}")

    # ------------------------------------------------------------------ lifecycle
    def start(self, spec: dict) -> dict:
        self.stop()
        rtsp_env = self.cfg.source.rtsp.to_dict()
        source = create_source(spec, base_dir=self.base_dir, rtsp_env=rtsp_env)  # may raise SourceError
        try:
            source.open()  # fail fast with a presenter-friendly message; the grabber handles later reconnects
        except SourceError:
            raise
        except Exception as exc:
            raise SourceError(f"Could not open the source: {type(exc).__name__}: {exc}") from exc
        self.source = source
        self.source_id = spec.get("source_id") or source_id_for(spec, source)
        self.source_spec = redact_mapping({k: v for k, v in spec.items() if k not in ("password", "username", "url")})
        self.source_spec["type"] = spec.get("type", source.kind)
        self.repos.sources.upsert(self.source_id, source.name, source.kind, source.masked_url, spec,
                                  spec.get("stream_profile", ""))
        self.zones = self.load_zones(self.source_id)
        self.spatial = SpatialAnalytics(self.zones, self.cfg.analytics.to_dict(), float(self.settings["dwell_threshold_seconds"]))
        self.tracker = create_tracker(self.cfg.tracking.to_dict(), float(self.settings["analytics_fps"]))
        self.tracker.reset()
        self.rules_engine.reset_cooldowns()
        rc = self.cfg.source.reconnect.to_dict()
        self.grabber = FrameGrabber(source, ReconnectPolicy(**rc), on_status=self._on_source_status)
        self.last_error = ""
        self.paused = False
        self.started_at = time.time()
        self._latest_fa = None
        self._stop.clear()
        self.grabber.start()
        self._thread = threading.Thread(target=self._run, name="pipeline", daemon=True)
        self._thread.start()
        self.health.set_component("source", True, f"{source.kind}: {source.masked_url}")
        logger.info(f"Pipeline started on {source.kind} source '{source.name}' ({source.masked_url}) id={self.source_id}")
        return self.state()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive() and threading.current_thread() is not self._thread:
            self._thread.join(timeout=5)
        if self.grabber:
            self.grabber.stop()
        if self.spatial:
            self.spatial.forget_all()
        self.grabber = None
        self.source = None
        self._thread = None
        with self._lock:
            self._latest_fa = None
        self.health.set_component("source", False, "stopped")

    def restart(self) -> dict:
        spec = dict(self.source_spec)
        if self.source and self.source.kind == "rtsp":
            # reuse the live source object (credentials are only in memory)
            src = self.source
            self.stop()
            self.source = src
            src.close()
            self.grabber = FrameGrabber(src, ReconnectPolicy(**self.cfg.source.reconnect.to_dict()), on_status=self._on_source_status)
            self.tracker.reset()
            self._stop.clear()
            self.grabber.start()
            self._thread = threading.Thread(target=self._run, name="pipeline", daemon=True)
            self._thread.start()
            return self.state()
        return self.start(spec)

    def shutdown(self) -> None:
        self.stop()
        self._maintenance_stop.set()
        if self.webhook:
            self.webhook.stop()

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # ------------------------------------------------------------------ callbacks
    def _on_source_status(self, old: SourceStatus, new: SourceStatus, source: VideoSource) -> None:
        ts = time.time()
        if new == SourceStatus.LIVE and old in (SourceStatus.DISCONNECTED, SourceStatus.DEGRADED):
            self.health.record_reconnect()
            self.tracker.reset() if self.tracker else None  # ids restart safely after a reconnect
            if self.spatial:
                self.spatial.forget_all()
        self.health.set_component("source", new in (SourceStatus.LIVE, SourceStatus.CONNECTING), f"{source.kind}: {new.value}")
        for cand in self.rules_engine.on_source_status(old.value, new.value, self.source_id, source.name, ts,
                                                       self.grabber.last_error if self.grabber else ""):
            try:
                self.events.create(cand, None)
            except Exception:
                logger.exception("Failed to record source status event")

    # ------------------------------------------------------------------ processing
    def _ensure_detector(self) -> Detector:
        if self.detector is None:
            model_cfg = self.cfg.model.to_dict()
            model_cfg.update({"confidence": self.settings["confidence"], "device": self.settings["device"],
                              "backend": self.settings["model_backend"], "image_size": self.settings["image_size"]})
            self.detector = create_detector(model_cfg, models_dir=resolve_path("models", self.base_dir))
            ok = not self.detector.error
            self.health.set_component("detector", True, f"{self.detector.backend} on {self.detector.device_label}"
                                      + (f" — {self.detector.error}" if self.detector.error else ""), degraded=not ok)
        return self.detector

    def _timestamp(self, frame) -> float:
        if self.clock == "media":
            return (self.started_at or 0.0) + frame.media_time
        return frame.captured_at

    def _run(self) -> None:
        try:
            detector = self._ensure_detector()
        except Exception as exc:  # pragma: no cover - create_detector never raises, defensive
            self.last_error = f"Detector failed to load: {exc}"
            self.health.record_error("detector", str(exc))
            return
        self.health.set_component("tracker", True, self.tracker.backend if self.tracker else "none")
        analysis_w = int(self.cfg.processing.analysis_max_width)
        stream_w = int(self.cfg.processing.stream_max_width)
        quality = int(self.cfg.processing.stream_jpeg_quality)
        next_tick = time.monotonic()
        last_cap_count, last_cap_time = 0, time.monotonic()
        while not self._stop.is_set():
            interval = 1.0 / max(0.5, float(self.settings["analytics_fps"]))
            now_m = time.monotonic()
            if now_m < next_tick:
                self._stop.wait(min(next_tick - now_m, 0.25))
                continue
            next_tick = max(next_tick + interval, now_m - interval)  # never accumulate lag
            grabber = self.grabber
            if grabber is None:
                break
            frame = grabber.latest(timeout=0.3)
            status = grabber.status
            # capture fps bookkeeping from the grabber's counters
            if now_m - last_cap_time >= 1.0:
                delta = grabber.frames_captured - last_cap_count
                for _ in range(delta):
                    self.health.record_capture()
                last_cap_count, last_cap_time = grabber.frames_captured, now_m
                self.health.dropped_frames = grabber.frames_dropped
            if frame is None or self.paused:
                self._publish_idle(status)
                if grabber.ended or status in (SourceStatus.ERROR,):
                    if grabber.ended:
                        self._publish_idle(SourceStatus.ENDED)
                    break
                continue
            if self.detector is None:  # settings changed the backend/device
                detector = self._ensure_detector()
            try:
                self._process(frame, status, detector, analysis_w, stream_w, quality)
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                self.health.record_error("pipeline", self.last_error)
                logger.exception("Frame processing failed")
                self._stop.wait(0.5)

    def _process(self, frame, status: SourceStatus, detector: Detector, analysis_w: int, stream_w: int, quality: int) -> None:
        ts = self._timestamp(frame)
        image = frame.image
        h, w = image.shape[:2]
        analysis_img, scale = resize_max_width(image, analysis_w)
        meta = frame.metadata
        if scale != 1.0 and meta.get("gt_boxes"):
            meta = dict(meta)
            meta["gt_boxes"] = [{**b, "box": tuple(v * scale for v in b["box"])} for b in meta["gt_boxes"]]
        dets = detector.detect(analysis_img, meta)
        if scale != 1.0:
            dets = [d.scaled(1.0 / scale) for d in dets]
        self.health.record_inference(detector.last_latency_ms)
        tracks = self.tracker.update(dets, ts)
        with self._lock:
            spatial = self.spatial
        for tid in self.tracker.expired_last_update:
            spatial.forget(tid, ts)
        fa = spatial.update(tracks, w, h, ts)
        if self._dwell_override_until and time.time() > self._dwell_override_until:
            self._end_dwell_override()
        candidates = self.rules_engine.evaluate(fa, self.source_id, self.source.name if self.source else "",
                                                frame.media_time if not self.source.is_live or self.source.kind == "file" else None)
        annotated = image.copy()
        draw_zones(annotated, self.zones, fa.zone_counts)
        draw_tracks(annotated, fa, bool(self.settings.get("trail_enabled")))
        draw_status_strip(annotated, self.source.name, status.value, detector.device_label,
                          self.health.inference.rate(), fa, local_display(now_utc(), self.cfg.app.get("timezone", "local")),
                          self.demo_mode)
        for cand in candidates:
            try:
                self.events.create(cand, annotated)
            except Exception:
                logger.exception("Event creation failed")
        self.evidence.push_frame(annotated, ts)
        stream_img, _ = resize_max_width(annotated, stream_w)
        ok, buf = cv2.imencode(".jpg", stream_img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        with self._lock:
            if ok:
                self._latest_jpeg = buf.tobytes()
            self._latest_raw = image
            self._latest_fa = fa
            self._state = self._build_state(status, fa, frame)

    def _publish_idle(self, status: SourceStatus) -> None:
        detail = self.grabber.last_error if self.grabber else ""
        title = {SourceStatus.CONNECTING: "Connecting to source…", SourceStatus.DISCONNECTED: "Source disconnected — reconnecting",
                 SourceStatus.DEGRADED: "Stream stalled — waiting for frames", SourceStatus.ENDED: "Video ended",
                 SourceStatus.ERROR: "Source error"}.get(status, "Paused" if self.paused else "Waiting for frames")
        with self._lock:
            base = self._latest_raw
            if base is not None:
                img = base.copy()
                draw_message(img, title, detail)
                ok, buf = cv2.imencode(".jpg", resize_max_width(img, 960)[0], [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                if ok:
                    self._latest_jpeg = buf.tobytes()
            elif not self._latest_jpeg:
                ok, buf = cv2.imencode(".jpg", placeholder_frame(title=title, detail=detail))
                if ok:
                    self._latest_jpeg = buf.tobytes()
            self._state = self._build_state(status, self._latest_fa, None)

    def _build_state(self, status: SourceStatus, fa: FrameAnalytics | None, frame) -> dict:
        det = self.detector
        src = self.source
        active_alerts = self.events.stats_today().get("active_alerts", 0) if self.events else 0
        state = {
            "running": True,
            "paused": self.paused,
            "source": {"id": self.source_id, "name": src.name if src else "", "kind": src.kind if src else "",
                       "masked_url": src.masked_url if src else "", "status": status.value,
                       "info": src.info.to_dict() if src and src.info else None,
                       "stream_profile": getattr(src, "stream_profile", ""),
                       "last_error": self.grabber.last_error if self.grabber else ""},
            "ai": {"backend": det.backend if det else "loading", "device": det.device_label if det else "-",
                   "confidence": self.settings["confidence"], "analytics_fps_target": self.settings["analytics_fps"],
                   "inference_fps": round(self.health.inference.rate(), 1), "latency_ms": round(det.last_latency_ms, 1) if det else 0,
                   "tracker": self.tracker.backend if self.tracker else "-", "fallback": bool(det.error) if det else False},
            "counts": {"people": fa.people_visible if fa else 0, "entries": fa.entries if fa else 0, "exits": fa.exits if fa else 0,
                       "occupancy": fa.occupancy if fa else 0, "zone_counts": fa.zone_counts if fa else {},
                       "line_counts": fa.line_counts if fa else {}, "active_alerts": active_alerts,
                       "average_dwell_seconds": round(self.spatial.dwell.average_dwell(), 1) if self.spatial else 0.0},
            "tracks": [tv.to_dict() for tv in fa.tracks] if fa else [],
            "zones": [z.to_dict() for z in self.zones],
            "frame": {"width": frame.width if frame else 0, "height": frame.height if frame else 0,
                      "media_time": round(frame.media_time, 1) if frame else None, "index": frame.index if frame else None},
            "time": local_display(now_utc(), self.cfg.app.get("timezone", "local")),
            "demo_mode": self.demo_mode,
            "last_error": self.last_error,
            "dwell_verify_active": bool(self._dwell_override_until and time.time() < self._dwell_override_until),
        }
        return state

    # ------------------------------------------------------------------ public reads
    def state(self) -> dict:
        with self._lock:
            if self._state and self.is_running:
                return dict(self._state)
        if self.is_running and self.grabber is not None:
            return self._build_state(self.grabber.status, None, None)
        return {"running": False, "paused": False, "source": {"id": self.source_id, "name": "", "kind": "", "status": "idle",
                                                              "masked_url": "", "info": None, "last_error": self.last_error},
                "ai": {"backend": self.detector.backend if self.detector else "-", "device": self.detector.device_label if self.detector else "-",
                       "confidence": self.settings["confidence"], "analytics_fps_target": self.settings["analytics_fps"],
                       "inference_fps": 0, "latency_ms": 0, "tracker": "-", "fallback": False},
                "counts": {"people": 0, "entries": 0, "exits": 0, "occupancy": 0, "zone_counts": {}, "line_counts": {},
                           "active_alerts": self.events.stats_today().get("active_alerts", 0), "average_dwell_seconds": 0.0},
                "tracks": [], "zones": [z.to_dict() for z in self.zones], "frame": {}, "demo_mode": self.demo_mode,
                "time": local_display(now_utc(), self.cfg.app.get("timezone", "local")), "last_error": self.last_error,
                "dwell_verify_active": False}

    def latest_jpeg(self) -> bytes:
        with self._lock:
            if self._latest_jpeg:
                return self._latest_jpeg
        ok, buf = cv2.imencode(".jpg", placeholder_frame(title="No source running", detail="Start a webcam, video file or RTSP camera from Demo or Settings"))
        return buf.tobytes() if ok else b""

    def snapshot_jpeg(self, raw: bool = True, max_width: int = 1280) -> bytes:
        """A single frame (raw = without overlays) for the zone editor."""
        with self._lock:
            img = self._latest_raw
        if img is None:
            return self.latest_jpeg()
        ok, buf = cv2.imencode(".jpg", resize_max_width(img, max_width)[0], [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        return buf.tobytes() if ok else b""

    # ------------------------------------------------------------------ demo helpers
    def reset_counts(self) -> None:
        with self._lock:
            if self.spatial:
                self.spatial.reset_counts()
        if self.tracker:
            self.tracker.reset()
        self.rules_engine.reset_cooldowns()
        logger.info("Counts reset by operator")

    def set_paused(self, paused: bool) -> None:
        self.paused = bool(paused)

    def verify_dwell(self, seconds: float | None = None) -> float:
        """Temporarily lower the dwell threshold so a presenter can trigger a dwell alert quickly."""
        seconds = float(seconds or self.cfg.demo.dwell_verify_threshold_seconds)
        if self._dwell_override_prev is None:
            self._dwell_override_prev = float(self.settings["dwell_threshold_seconds"])
        self.settings["dwell_threshold_seconds"] = seconds
        self._sync_rule_thresholds()
        self._dwell_override_until = time.time() + 120
        logger.info(f"Dwell verification: threshold temporarily {seconds}s for 2 minutes")
        return seconds

    def _end_dwell_override(self) -> None:
        if self._dwell_override_prev is not None:
            self.settings["dwell_threshold_seconds"] = self._dwell_override_prev
            self._sync_rule_thresholds()
        self._dwell_override_prev = None
        self._dwell_override_until = 0.0

    def fire_test_event(self, rule_type: str = "restricted_zone_intrusion") -> dict:
        rt = RuleType(rule_type)
        rule = self.rules_engine.rule(rt) or default_rules()[0]
        with self._lock:
            frame = self._latest_raw.copy() if self._latest_raw is not None else placeholder_frame(title="TEST EVENT")
        draw_message(frame, "TEST EVENT — pipeline verification", "generated by the operator, not by detection")
        cand = EventCandidate(rule, rt.value, f"TEST: {rule.name} (operator-generated verification event)", time.time(),
                              rule.severity, self.source_id or "none", self.source.name if self.source else "No source",
                              None, None, None, None, {"test": True, "simulated": True})
        return self.events.create(cand, frame)

    # ------------------------------------------------------------------ maintenance
    def _maintenance_loop(self) -> None:
        interval = max(60, int(self.cfg.evidence.cleanup_interval_minutes) * 60)
        last_cleanup = 0.0
        last_health = 0.0
        while not self._maintenance_stop.wait(5.0):
            now = time.time()
            try:
                if now - last_cleanup >= interval:
                    self.evidence.cleanup()
                    self.events.purge_older_than(int(self.settings["retention_days"]))
                    last_cleanup = now
                if now - last_health >= 60:
                    snap = self.health.snapshot()
                    st = self.state()
                    self.repos.health.add({"source_id": st["source"]["id"], "source_status": st["source"]["status"],
                                           "capture_fps": snap["capture_fps"], "inference_fps": snap["inference_fps"],
                                           "latency_ms": snap["latency_ms"], "dropped_frames": snap["dropped_frames"],
                                           "reconnects": snap["reconnects"], "cpu_percent": snap["system"]["cpu_percent"],
                                           "memory_percent": snap["system"]["memory_percent"], "disk_free_mb": snap["system"]["disk_free_mb"],
                                           "detector": st["ai"]["backend"], "device": st["ai"]["device"], "details": {}})
                    self.repos.health.prune()
                    last_health = now
                self.health.set_component("database", self.repos.db.status()["ok"], str(self.repos.db.path))
            except Exception:
                logger.exception("Maintenance task failed")

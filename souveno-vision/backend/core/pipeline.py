"""Vision Pipeline orchestrator — wires together every layer described in
the architecture:

    VIDEO SOURCE -> DETECTOR -> TRACKER -> ZONE ENGINE -> ACTIVITY ENGINE
    -> RULE ENGINE -> EVENT ENGINE -> METRICS -> (AI REASONING at video end)
    -> DASHBOARD / ALERTS

`VisionPipeline.process_frame()` is the single per-frame entry point used
by both the live analysis websocket and (eventually) a live RTSP loop —
nothing here depends on the frame having come from a file.
"""
from __future__ import annotations

from collections import deque

import cv2
import numpy as np
from loguru import logger
from sqlalchemy.orm import Session

from backend.core import geometry
from backend.core.activity import ActivityEngine
from backend.core.detector import Detector
from backend.core.events import EventEngine, format_hms
from backend.core.metrics import MetricsAggregator
from backend.core.rules import RuleEngine
from backend.core.spill import SpillDetector
from backend.core.tables import TableTracker
from backend.core.tracker import Tracker, TrackedObject
from backend.core.zones import ZoneDef, ZoneEngine
from config.rules_config import get_active_thresholds

TRACK_TIMEOUT_SECONDS = 2.0
TRAIL_LENGTH = 40

ZONE_COLOR_BGR_DEFAULT = (255, 167, 59)


def _hex_to_bgr(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return ZONE_COLOR_BGR_DEFAULT
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return (b, g, r)


class VisionPipeline:
    def __init__(self, db: Session, session_id: int, camera_id: str, zones: list[ZoneDef],
                 detector: Detector, tracker: Tracker, frame_width: int, frame_height: int,
                 demo_mode: bool = True, alert_hook=None):
        self.db = db
        self.session_id = session_id
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.demo_mode = demo_mode

        self.detector = detector
        self.tracker = tracker
        self.zone_engine = ZoneEngine(zones)
        self.activity_engine = ActivityEngine()
        self.thresholds = get_active_thresholds()
        self.table_tracker = TableTracker(clearing_delay_seconds=self.thresholds["table_clearing_delay_seconds"])
        self.rule_engine = RuleEngine(self.thresholds)
        self.event_engine = EventEngine(db, session_id, camera_id, alert_hook=alert_hook)
        self.metrics = MetricsAggregator()
        self.spill_detector = SpillDetector()

        self.track_roles: dict[int, str] = {}
        self.track_meta: dict[int, dict] = {}
        self.last_seen: dict[int, float] = {}
        self.trail_history: dict[int, deque] = {}
        self._active_spills: dict[str, str] = {}  # spill_id -> event_engine key
        self._spill_counter = 0

        self.table_zone_ids = [z.zone_id for z in zones if z.zone_type == "TABLE"]
        self.queue_zone_ids = [z.zone_id for z in zones if z.zone_type == "QUEUE_ZONE"]
        self.counter_zone_ids = [z.zone_id for z in zones if z.zone_type == "COUNTER_ZONE"]
        self.entrance_line_ids = [z.zone_id for z in zones if z.zone_type == "ENTRANCE_LINE"]
        self._has_entrance_line = bool(self.entrance_line_ids)

    # ------------------------------------------------------------------ role overrides (Phase 9)
    def set_role(self, track_id: int, role: str):
        self.track_roles[track_id] = role

    def _suggested_role(self, zones_now: set[str]) -> str:
        for zone_id in zones_now:
            zone = self.zone_engine.zone_by_id(zone_id)
            if zone and zone.zone_type in ("PREP_ZONE", "COUNTER_ZONE"):
                return "STAFF"
        for zone_id in zones_now:
            zone = self.zone_engine.zone_by_id(zone_id)
            if zone and zone.zone_type == "DINING_ZONE":
                return "CUSTOMER"
        return "UNKNOWN"

    # ------------------------------------------------------------------ spill (Phase 13)
    def trigger_spill(self, zone_id: str, timestamp: float, confidence: float = 0.55) -> dict:
        self._spill_counter += 1
        spill_id = f"spill-{self._spill_counter}"
        key = f"spill:{spill_id}"
        event = self.event_engine.open_event(key, "VISIBLE_SPILL_DETECTED", zone_id, [], timestamp,
                                              severity="warning", confidence=confidence,
                                              metadata={"experimental": True, "source": "manual_demo_trigger"})
        self._active_spills[spill_id] = key
        self.metrics.record_spill()
        return {"spill_id": spill_id, "event": event}

    def resolve_spill(self, spill_id: str, timestamp: float) -> dict | None:
        key = self._active_spills.pop(spill_id, None)
        if not key:
            return None
        closed = self.event_engine.close_event(key, timestamp)
        resolved = self.event_engine.instant_event("SPILL_RESOLVED", closed["zone_id"] if closed else None,
                                                     [], timestamp, severity="info",
                                                     metadata={"original_event": closed["event_id"] if closed else None})
        return resolved

    # ------------------------------------------------------------------ per-event metric bookkeeping
    def _account_event(self, ev: dict):
        et = ev["event_type"]
        if et == "POTENTIAL_IDLE_STAFF":
            if ev["status"] == "open":
                self.metrics.record_idle_opened()
            elif ev["status"] == "closed":
                self.metrics.record_idle_closed(ev.get("duration_seconds") or 0)
        elif et == "POTENTIAL_TABLE_CLEARING_DELAY" and ev["status"] == "open":
            self.metrics.record_clearing_delay()
        elif et == "POTENTIAL_PICKUP_DELAY" and ev["status"] == "open":
            self.metrics.record_pickup_delay()
        elif et == "POTENTIAL_QUEUE_ABANDONMENT":
            self.metrics.record_abandonment()

    # ------------------------------------------------------------------ main per-frame step
    def process_frame(self, frame: np.ndarray, frame_idx: int, timestamp: float) -> dict:
        tracks = self.tracker.track(frame)
        people = [t for t in tracks if t.class_name == "person"]
        objects = [t for t in tracks if t.class_name != "person"]
        w, h = self.frame_width, self.frame_height

        emitted: list[dict] = []
        zone_counts: dict[str, int] = {z.zone_id: 0 for z in self.zone_engine.polygon_zones}
        track_render: list[dict] = []

        for t in people:
            self.last_seen[t.track_id] = timestamp
            self._update_trail(t)
            norm_point = self._normalize(geometry.centroid_of_box(t.box), w, h)

            if t.track_id not in self.track_meta:
                self.track_meta[t.track_id] = {"first_seen": timestamp, "queue_entered_at": None,
                                                "reached_counter": False}
                emitted.append(self.event_engine.instant_event("PERSON_ENTER", None, [t.track_id], timestamp,
                                                                 severity="info", confidence=t.confidence))

            zr = self.zone_engine.update(t.track_id, norm_point, timestamp)
            activity = self.activity_engine.update(t.track_id, norm_point, timestamp)

            for zone_id in zr.zones_now:
                zone_counts[zone_id] = zone_counts.get(zone_id, 0) + 1

            role = self.track_roles.get(t.track_id) or self._suggested_role(zr.zones_now)

            for zone_id in zr.zones_entered:
                zone = self.zone_engine.zone_by_id(zone_id)
                emitted.append(self.event_engine.instant_event("ZONE_ENTER", zone_id, [t.track_id], timestamp,
                                                                 metadata={"zone_type": zone.zone_type if zone else ""}))
                if zone and zone.zone_type == "QUEUE_ZONE":
                    self.track_meta[t.track_id]["queue_entered_at"] = timestamp
                    self.track_meta[t.track_id]["reached_counter"] = False
                if zone and zone.zone_type == "COUNTER_ZONE":
                    self.track_meta[t.track_id]["reached_counter"] = True

            for zone_id in zr.zones_exited:
                zone = self.zone_engine.zone_by_id(zone_id)
                emitted.append(self.event_engine.instant_event("ZONE_EXIT", zone_id, [t.track_id], timestamp,
                                                                 metadata={"zone_type": zone.zone_type if zone else ""}))
                if zone and zone.zone_type == "QUEUE_ZONE":
                    entered_at = self.track_meta[t.track_id].get("queue_entered_at")
                    if entered_at is not None:
                        dwell = timestamp - entered_at
                        self.metrics.record_queue_dwell(dwell)
                        reached = self.track_meta[t.track_id].get("reached_counter", False)
                        intents = self.rule_engine.evaluate_abandonment(t.track_id, dwell, reached, timestamp)
                        emitted.extend(self.event_engine.apply_intents(intents))
                        self.track_meta[t.track_id]["queue_entered_at"] = None

            for crossing in zr.line_crossings:
                direction = crossing["direction"]
                self.metrics.record_footfall(direction)
                emitted.append(self.event_engine.instant_event(
                    "FOOTFALL_ENTER" if direction == "enter" else "FOOTFALL_EXIT",
                    crossing["zone_id"], [t.track_id], timestamp, metadata={"direction": direction}))

            for zone_id in zr.zones_now:
                zone = self.zone_engine.zone_by_id(zone_id)
                if zone and zone.zone_type == "PREP_ZONE":
                    intents = self.rule_engine.evaluate_idle_staff(t.track_id, zone_id, zone.zone_type, role,
                                                                     activity["idle_duration"], timestamp)
                    emitted.extend(self.event_engine.apply_intents(intents))

            dwell_by_zone = {zid: self.zone_engine.dwell_seconds(t.track_id, zid, timestamp) for zid in zr.zones_now}
            track_render.append({
                "track_id": t.track_id, "class_name": t.class_name, "box": t.box,
                "confidence": t.confidence, "role": role, "zones": sorted(zr.zones_now),
                "dwell_by_zone": dwell_by_zone, "is_moving": activity["is_moving"],
            })

        for o in objects:
            self.last_seen[o.track_id] = timestamp
            norm_point = self._normalize(geometry.box_center(o.box), w, h)
            zr = self.zone_engine.update(o.track_id, norm_point, timestamp)
            for zone_id in zr.zones_now:
                zone = self.zone_engine.zone_by_id(zone_id)
                if zone and zone.zone_type == "PICKUP_ZONE":
                    dwell = self.zone_engine.dwell_seconds(o.track_id, zone_id, timestamp)
                    intents = self.rule_engine.evaluate_pickup(o.track_id, zone_id, dwell, timestamp)
                    emitted.extend(self.event_engine.apply_intents(intents))
            track_render.append({
                "track_id": o.track_id, "class_name": o.class_name, "box": o.box,
                "confidence": o.confidence, "role": "OBJECT", "zones": sorted(zr.zones_now),
                "dwell_by_zone": {}, "is_moving": False,
            })

        # stale-track cleanup
        stale = [tid for tid, last in self.last_seen.items() if timestamp - last > TRACK_TIMEOUT_SECONDS]
        for tid in stale:
            if tid in self.track_meta:
                emitted.append(self.event_engine.instant_event("PERSON_EXIT", None, [tid], timestamp, severity="info"))
            self.zone_engine.forget_track(tid)
            self.activity_engine.forget_track(tid)
            self.last_seen.pop(tid, None)
            self.track_meta.pop(tid, None)
            self.trail_history.pop(tid, None)

        # tables
        table_statuses = {}
        for table_id in self.table_zone_ids:
            occupancy = zone_counts.get(table_id, 0)
            status = self.table_tracker.update(table_id, occupancy, timestamp)
            table_statuses[table_id] = status
            intents = self.rule_engine.evaluate_table(table_id, status.state.value, status.vacated_seconds_ago, timestamp)
            emitted.extend(self.event_engine.apply_intents(intents))

        # queue rule (zone-level, once per queue zone)
        for queue_zone_id in self.queue_zone_ids:
            count = zone_counts.get(queue_zone_id, 0)
            self.metrics.peak_queue = max(self.metrics.peak_queue, count)
            intents = self.rule_engine.evaluate_queue(queue_zone_id, count, self.metrics.peak_queue, timestamp)
            emitted.extend(self.event_engine.apply_intents(intents))

        for ev in emitted:
            self._account_event(ev)

        counts_by_type: dict[str, int] = {}
        for zone_id, count in zone_counts.items():
            zone = self.zone_engine.zone_by_id(zone_id)
            if zone and zone.zone_type != "TABLE":
                counts_by_type[zone.zone_type] = counts_by_type.get(zone.zone_type, 0) + count

        prep_staff_count = counts_by_type.get("PREP_ZONE", 0)
        total_queue = sum(zone_counts.get(z, 0) for z in self.queue_zone_ids)
        current_occupancy = max(0, self.metrics.footfall_in - self.metrics.footfall_out) if self._has_entrance_line else len(people)

        self.metrics.update_live(
            people_visible=len(people), zone_counts=counts_by_type, active_tracks=len(tracks),
            queue_count=total_queue, tables_status=table_statuses, prep_staff_count=prep_staff_count,
            potential_idle_staff_now=len(self.rule_engine._idle_open), current_occupancy=current_occupancy,
        )

        annotated = self._draw_overlay(frame.copy(), track_render, table_statuses, timestamp)

        return {
            "frame_index": frame_idx,
            "timestamp": round(timestamp, 2),
            "video_time_label": format_hms(timestamp),
            "new_events": [self._public_event(e) for e in emitted],
            "metrics": self.metrics.snapshot(),
            "tables": {tid: {"state": s.state.value, "vacated_seconds_ago": s.vacated_seconds_ago}
                       for tid, s in table_statuses.items()},
            "device": self.detector.device_label,
        }, annotated

    @staticmethod
    def _public_event(e: dict) -> dict:
        return {k: v for k, v in e.items() if k not in ("db_id", "key")}

    @staticmethod
    def _normalize(point, w, h):
        return (point[0] / w, point[1] / h)

    def _update_trail(self, t: TrackedObject):
        trail = self.trail_history.setdefault(t.track_id, deque(maxlen=TRAIL_LENGTH))
        cx, cy = geometry.centroid_of_box(t.box)
        trail.append((int(cx), int(cy)))

    # ------------------------------------------------------------------ drawing
    def _draw_overlay(self, frame: np.ndarray, tracks: list[dict], table_statuses: dict, timestamp: float) -> np.ndarray:
        h, w = frame.shape[:2]
        overlay = frame.copy()

        for zone in self.zone_engine.zones:
            color = _hex_to_bgr(zone.color)
            pts = np.array([[int(p[0] * w), int(p[1] * h)] for p in zone.points], dtype=np.int32)
            if zone.shape_type == "polygon" and len(pts) >= 3:
                cv2.fillPoly(overlay, [pts], color)
                cv2.polylines(frame, [pts], True, color, 2)
                label_pos = tuple(pts[0])
                cv2.putText(frame, zone.name, (label_pos[0] + 4, label_pos[1] + 18),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
            elif zone.shape_type == "line" and len(pts) >= 2:
                cv2.line(frame, tuple(pts[0]), tuple(pts[1]), color, 3)
                cv2.putText(frame, zone.name, (pts[0][0] + 4, pts[0][1] - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
        cv2.addWeighted(overlay, 0.12, frame, 0.88, 0, frame)

        for table_id, status in table_statuses.items():
            zone = self.zone_engine.zone_by_id(table_id)
            if not zone:
                continue
            pts = np.array([[int(p[0] * w), int(p[1] * h)] for p in zone.points], dtype=np.int32)
            state_colors = {"OCCUPIED": (60, 60, 220), "VACATED": (0, 200, 255),
                             "CLEARING_DELAY": (0, 0, 255), "AVAILABLE": (100, 200, 100)}
            color = state_colors.get(status.state.value, (200, 200, 200))
            cv2.polylines(frame, [pts], True, color, 2)
            label = f"{zone.name}: {status.state.value}"
            if status.vacated_seconds_ago is not None:
                label += f" ({format_hms(status.vacated_seconds_ago)} ago)"
            cv2.putText(frame, label, (pts[0][0], pts[0][1] + 34),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)

        for tid, trail in self.trail_history.items():
            if len(trail) >= 2:
                pts = np.array(list(trail), dtype=np.int32)
                cv2.polylines(frame, [pts], False, (255, 210, 90), 2, cv2.LINE_AA)

        for t in tracks:
            x1, y1, x2, y2 = [int(v) for v in t["box"]]
            is_person = t["class_name"] == "person"
            box_color = (60, 220, 120) if is_person else (200, 180, 60)
            cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)

            if is_person:
                title = f"Person #{t['track_id']:03d}"
            else:
                title = f"{t['class_name'].title()} #{t['track_id']}"
            cv2.rectangle(frame, (x1, y1 - 20), (x1 + max(140, len(title) * 9), y1), box_color, -1)
            cv2.putText(frame, title, (x1 + 4, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (10, 10, 10), 1, cv2.LINE_AA)

            sub_lines = []
            if t["dwell_by_zone"]:
                zone_id, dwell = max(t["dwell_by_zone"].items(), key=lambda kv: kv[1])
                sub_lines.append(f"Dwell: {format_hms(dwell)}")
                sub_lines.append(f"Zone: {zone_id}")
            elif t["zones"]:
                sub_lines.append(f"Zone: {t['zones'][0]}")
            if t["role"] not in ("UNKNOWN", "OBJECT"):
                sub_lines.append(t["role"])

            for i, line in enumerate(sub_lines):
                cv2.putText(frame, line, (x1, y2 + 16 + i * 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                            (255, 255, 255), 1, cv2.LINE_AA)

        self._draw_branding(frame, timestamp)
        return frame

    def _draw_branding(self, frame: np.ndarray, timestamp: float):
        h, w = frame.shape[:2]
        cv2.rectangle(frame, (0, 0), (w, 34), (24, 24, 24), -1)
        cv2.putText(frame, "SOUVENO VISION — LIVE ANALYSIS", (10, 23), cv2.FONT_HERSHEY_SIMPLEX,
                    0.6, (255, 255, 255), 1, cv2.LINE_AA)
        right_text = f"{format_hms(timestamp)}  |  {self.detector.device_label}"
        (tw, _), _ = cv2.getTextSize(right_text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
        cv2.putText(frame, right_text, (w - tw - 10, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                    (180, 220, 255), 1, cv2.LINE_AA)
        if self.demo_mode:
            cv2.rectangle(frame, (0, h - 26), (110, h), (0, 100, 220), -1)
            cv2.putText(frame, "DEMO MODE", (8, h - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                        (255, 255, 255), 1, cv2.LINE_AA)

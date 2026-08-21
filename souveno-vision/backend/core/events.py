"""Event Engine (Phase 14) — the single place that turns rule intents into
persisted `Event` rows, `Alert` rows, and a human-readable timeline. This
is the only layer that touches the database on the hot path, which keeps
RuleEngine/ZoneEngine/ActivityEngine trivially unit-testable.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Callable, Optional

from sqlalchemy.orm import Session

from backend.db import crud


def format_hms(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return str(timedelta(seconds=seconds))


LABEL_TEMPLATES = {
    "PERSON_ENTER": "Person #{track} entered the scene",
    "PERSON_EXIT": "Person #{track} left the scene",
    "ZONE_ENTER": "Person #{track} entered {zone}",
    "ZONE_EXIT": "Person #{track} exited {zone}",
    "QUEUE_WARNING": "Queue threshold reached in {zone}",
    "QUEUE_CRITICAL": "Queue critically long in {zone}",
    "QUEUE_CLEARED": "Queue cleared in {zone}",
    "POTENTIAL_QUEUE_ABANDONMENT": "Potential queue abandonment — Person #{track}",
    "POTENTIAL_IDLE_STAFF": "Potential idle staff detected in {zone} — Person #{track}",
    "TABLE_OCCUPIED": "{zone} occupied",
    "TABLE_VACATED": "{zone} vacated",
    "POTENTIAL_TABLE_CLEARING_DELAY": "Potential clearing delay — {zone}",
    "POTENTIAL_PICKUP_DELAY": "Potential unattended pickup item in {zone}",
    "VISIBLE_SPILL_DETECTED": "Experimental: possible spill detected in {zone}",
    "SPILL_RESOLVED": "Spill area in {zone} marked resolved",
    "FOOTFALL_ENTER": "Customer entered ({direction})",
    "FOOTFALL_EXIT": "Customer exited ({direction})",
}


def humanize(event: dict) -> str:
    template = LABEL_TEMPLATES.get(event["event_type"], event["event_type"])
    track = event["track_ids"][0] if event.get("track_ids") else "?"
    zone = event.get("zone_id") or "the venue"
    direction = event.get("metadata", {}).get("direction", "")
    try:
        return template.format(track=track, zone=zone, direction=direction)
    except (KeyError, IndexError):
        return event["event_type"]


class EventEngine:
    def __init__(self, db: Session, session_id: int, camera_id: str = "CAM-DEMO-01",
                 alert_hook: Optional[Callable[[dict], None]] = None):
        self.db = db
        self.session_id = session_id
        self.camera_id = camera_id
        self.alert_hook = alert_hook
        self._open: dict[str, dict] = {}
        self._open_alert_ids: dict[str, int] = {}
        self.timeline: list[dict] = []

    def apply_intents(self, intents: list[dict]) -> list[dict]:
        emitted = []
        for intent in intents:
            action = intent["action"]
            if action == "open":
                emitted.append(self.open_event(
                    intent["key"], intent["event_type"], intent["zone_id"], intent["track_ids"],
                    intent["timestamp"], intent["severity"], intent["confidence"], intent["metadata"],
                ))
            elif action == "close":
                closed = self.close_event(intent["key"], intent["timestamp"])
                if closed:
                    emitted.append(closed)
            elif action == "instant":
                emitted.append(self.instant_event(
                    intent["event_type"], intent["zone_id"], intent["track_ids"], intent["timestamp"],
                    intent["severity"], intent["confidence"], intent["metadata"],
                ))
        return [e for e in emitted if e]

    def open_event(self, key: str, event_type: str, zone_id: str, track_ids: list[int],
                    start_time: float, severity: str, confidence: float, metadata: dict) -> dict:
        if key in self._open:
            return self._open[key]
        row = crud.create_event(self.db, self.session_id, self.camera_id, event_type, zone_id,
                                 track_ids, start_time, severity, confidence, metadata)
        event = crud.event_to_dict(row)
        event["db_id"] = row.id
        event["key"] = key
        event["label"] = humanize(event)
        self._open[key] = event
        self._log(event)
        if severity in ("warning", "critical"):
            alert = crud.create_alert(self.db, self.session_id, row.id, event_type, event["label"],
                                       f"Started at {format_hms(start_time)}", severity)
            self._open_alert_ids[key] = alert.id
            if self.alert_hook:
                self.alert_hook({"title": event["label"], "severity": severity, "event_type": event_type,
                                  "zone_id": zone_id, "started": format_hms(start_time)})
        return event

    def close_event(self, key: str, end_time: float) -> Optional[dict]:
        event = self._open.pop(key, None)
        if not event:
            return None
        row = crud.close_event(self.db, event["db_id"], end_time)
        updated = crud.event_to_dict(row)
        updated["db_id"] = row.id
        updated["key"] = key
        updated["label"] = humanize(updated) + " — resolved"
        self._log(updated)
        alert_id = self._open_alert_ids.pop(key, None)
        if alert_id:
            crud.resolve_alert(self.db, alert_id)
        return updated

    def instant_event(self, event_type: str, zone_id: str, track_ids: list[int], timestamp: float,
                       severity: str = "info", confidence: float = 1.0, metadata: Optional[dict] = None) -> dict:
        row = crud.create_event(self.db, self.session_id, self.camera_id, event_type, zone_id,
                                 track_ids, timestamp, severity, confidence, metadata or {})
        row = crud.close_event(self.db, row.id, timestamp)
        event = crud.event_to_dict(row)
        event["db_id"] = row.id
        event["label"] = humanize(event)
        self._log(event)
        return event

    def active_events(self) -> list[dict]:
        return list(self._open.values())

    def _log(self, event: dict):
        entry = {
            "event_id": event["event_id"],
            "event_type": event["event_type"],
            "zone_id": event["zone_id"],
            "track_ids": event["track_ids"],
            "timestamp": event.get("end_time") if event.get("status") == "closed" else event["start_time"],
            "video_time_label": format_hms(event.get("end_time") if event.get("status") == "closed" else event["start_time"]),
            "severity": event["severity"],
            "label": event["label"],
            "status": event["status"],
        }
        self.timeline.append(entry)

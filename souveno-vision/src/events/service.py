"""Layer 7 — EventService: EventCandidate -> persisted Event (+ evidence,
acknowledgement audit trail, live feed subscribers, webhook fan-out, CSV export)."""
from __future__ import annotations

import threading
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

import numpy as np
from loguru import logger

from src.events.evidence import EvidenceManager
from src.events.webhook import WebhookDispatcher
from src.rules.models import EventCandidate
from src.storage.repositories import Repositories
from src.utils.time_utils import utc_iso

OPEN_STATUSES = ("new", "acknowledged")


def new_event_id() -> str:
    return f"EV-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


class EventService:
    def __init__(self, repos: Repositories, evidence: EvidenceManager | None = None,
                 webhook: WebhookDispatcher | None = None, feed_size: int = 200):
        self.repos = repos
        self.evidence = evidence
        self.webhook = webhook
        self.feed: deque = deque(maxlen=feed_size)
        self._subscribers: list[Callable[[dict], None]] = []
        self._lock = threading.Lock()
        self.created_total = 0
        if self.evidence is not None:
            self.evidence.on_clip_done = self._attach_clip

    # ---- subscribers ------------------------------------------------------------------
    def subscribe(self, callback: Callable[[dict], None]) -> None:
        self._subscribers.append(callback)

    def _emit(self, event: dict) -> None:
        with self._lock:
            self.feed.appendleft(event)
        for cb in list(self._subscribers):
            try:
                cb(event)
            except Exception:
                logger.exception("Event subscriber failed")

    # ---- creation ------------------------------------------------------------------------
    def create(self, candidate: EventCandidate, annotated_frame: Optional[np.ndarray] = None) -> dict:
        event_id = new_event_id()
        ts_iso = utc_iso(datetime.fromtimestamp(candidate.timestamp, tz=timezone.utc))
        record = {
            "event_id": event_id, "event_type": candidate.event_type, "title": candidate.title,
            "rule_id": candidate.rule.rule_id, "source_id": candidate.source_id, "source_name": candidate.source_name,
            "zone_id": candidate.zone_id, "zone_name": candidate.zone_name, "track_id": candidate.track_id,
            "timestamp": ts_iso, "media_time": candidate.media_time, "severity": candidate.severity.value,
            "confidence": candidate.confidence, "snapshot_path": None, "clip_path": None, "status": "new",
            "acknowledged_by": None, "acknowledged_at": None, "notes": "",
            "metadata": {**candidate.metadata, "rule_name": candidate.rule.name, "notify": candidate.notify},
        }
        if candidate.evidence_required and self.evidence is not None and annotated_frame is not None:
            caption = f"{candidate.source_name} | {candidate.zone_name or '-'} | Person {candidate.track_id or '-'}"
            record["snapshot_path"] = self.evidence.save_snapshot(event_id, candidate.event_type, annotated_frame, caption)
            if self.evidence.request_clip(event_id, candidate.event_type):
                record["metadata"]["clip_pending"] = True
        saved = self.repos.events.insert(record)
        self.created_total += 1
        logger.info(f"EVENT {saved['severity'].upper()} {saved['event_type']} — {saved['title']} [{saved['event_id']}]")
        self._emit(saved)
        if candidate.notify and self.webhook is not None:
            self.webhook.enqueue(self.to_webhook_payload(saved))
        return saved

    def _attach_clip(self, event_id: str, path: str) -> None:
        self.repos.events.update_paths(event_id, clip_path=path)
        updated = self.repos.events.get(event_id)
        if updated:
            with self._lock:
                for i, e in enumerate(self.feed):
                    if e["event_id"] == event_id:
                        self.feed[i] = updated
                        break

    @staticmethod
    def to_webhook_payload(event: dict) -> dict:
        return {"type": "souveno.vision.event", "version": 1, "sent_at": utc_iso(),
                "event": {k: v for k, v in event.items() if k not in ("snapshot_path", "clip_path")},
                "evidence": {"snapshot": bool(event.get("snapshot_path")), "clip": bool(event.get("clip_path"))},
                "privacy": "anonymous camera-local track IDs; no identity data"}

    # ---- workflow ------------------------------------------------------------------------
    def acknowledge(self, event_id: str, actor: str = "operator", note: str = "") -> Optional[dict]:
        return self._transition(event_id, "acknowledged", actor, note)

    def resolve(self, event_id: str, actor: str = "operator", note: str = "") -> Optional[dict]:
        return self._transition(event_id, "resolved", actor, note)

    def dismiss(self, event_id: str, actor: str = "operator", note: str = "") -> Optional[dict]:
        return self._transition(event_id, "dismissed", actor, note)

    def reopen(self, event_id: str, actor: str = "operator", note: str = "") -> Optional[dict]:
        return self._transition(event_id, "new", actor, note, action="reopened")

    def _transition(self, event_id: str, status: str, actor: str, note: str, action: str | None = None) -> Optional[dict]:
        existing = self.repos.events.get(event_id)
        if not existing:
            return None
        updated = self.repos.events.set_status(event_id, status, actor, note)
        self.repos.acks.add(event_id, action or status, actor or "operator", note)  # audit log
        logger.info(f"Event {event_id} {action or status} by {actor or 'operator'}")
        with self._lock:
            for i, e in enumerate(self.feed):
                if e["event_id"] == event_id:
                    self.feed[i] = updated
                    break
        return updated

    # ---- queries -------------------------------------------------------------------------
    def recent(self, limit: int = 50) -> list[dict]:
        with self._lock:
            return list(self.feed)[:limit]

    def active_alerts(self, severities=("medium", "high", "critical")) -> list[dict]:
        return [e for e in self.repos.events.list({"status": "new"}, limit=500) if e["severity"] in severities]

    def stats_today(self, tz_offset_hours: float = 0.0) -> dict:
        start = (datetime.now(timezone.utc) + timedelta(hours=tz_offset_hours)).replace(hour=0, minute=0, second=0, microsecond=0)
        start = start - timedelta(hours=tz_offset_hours)
        f = {"date_from": utc_iso(start)}
        by_type = self.repos.events.count_by("event_type", f)
        return {"total_today": self.repos.events.count(f), "by_type": by_type,
                "restricted_violations_today": by_type.get("restricted_zone_intrusion", 0),
                "active_alerts": len(self.active_alerts()),
                "by_severity": self.repos.events.count_by("severity", f)}

    def export_csv(self, filters: dict | None = None) -> str:
        return self.repos.events.export_csv(filters)

    def purge_older_than(self, days: int) -> int:
        cutoff = utc_iso(datetime.now(timezone.utc) - timedelta(days=days))
        for _, snap, clip in self.repos.events.paths_older_than(cutoff):
            for p in (snap, clip):
                if p:
                    try:
                        from pathlib import Path
                        Path(p).unlink(missing_ok=True)
                    except OSError:
                        pass
        return self.repos.events.delete_older_than(cutoff)

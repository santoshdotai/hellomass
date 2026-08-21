"""Rule Engine (Phase 15) — configurable, data-driven thresholds turn raw
zone/activity/table signals into event *intents*.

RuleEngine is intentionally pure/stateless-with-respect-to-persistence: it
never touches the database. It returns a list of "intent" dicts describing
what should open, close, or fire instantaneously; `EventEngine` (events.py)
is the only thing that talks to storage. This split is what makes the
idle/queue/table rules unit-testable without a database.

Intent dict shape:
    {"action": "open"|"close"|"instant", "key": str, "event_type": str,
     "zone_id": str, "track_ids": list[int], "timestamp": float,
     "severity": str, "confidence": float, "metadata": dict}
"""
from __future__ import annotations

from config.rules_config import get_active_thresholds


def _intent(action, key=None, event_type=None, zone_id=None, track_ids=None,
            timestamp=0.0, severity="info", confidence=1.0, metadata=None):
    return {
        "action": action,
        "key": key,
        "event_type": event_type,
        "zone_id": zone_id,
        "track_ids": track_ids or [],
        "timestamp": timestamp,
        "severity": severity,
        "confidence": confidence,
        "metadata": metadata or {},
    }


class RuleEngine:
    def __init__(self, thresholds: dict | None = None):
        self.thresholds = thresholds or get_active_thresholds()
        self._queue_level: dict[str, str] = {}
        self._idle_open: set[str] = set()
        self._table_open: set[str] = set()
        self._pickup_open: set[str] = set()

    # ---------------------------------------------------------- queue
    def evaluate_queue(self, zone_id: str, count: int, peak: int, timestamp: float) -> list[dict]:
        intents = []
        level = self._queue_level.get(zone_id, "normal")
        warn_t = self.thresholds["queue_warning_count"]
        crit_t = self.thresholds["queue_critical_count"]

        if count >= crit_t:
            if level != "critical":
                if level == "warning":
                    intents.append(_intent("close", key=f"queue_warning:{zone_id}", timestamp=timestamp))
                intents.append(_intent("open", key=f"queue_critical:{zone_id}", event_type="QUEUE_CRITICAL",
                                        zone_id=zone_id, timestamp=timestamp, severity="critical",
                                        metadata={"count": count, "threshold": crit_t}))
                level = "critical"
        elif count >= warn_t:
            if level == "normal":
                intents.append(_intent("open", key=f"queue_warning:{zone_id}", event_type="QUEUE_WARNING",
                                        zone_id=zone_id, timestamp=timestamp, severity="warning",
                                        metadata={"count": count, "threshold": warn_t}))
                level = "warning"
        else:
            if level in ("warning", "critical"):
                intents.append(_intent("close", key=f"queue_{level}:{zone_id}", timestamp=timestamp))
                intents.append(_intent("instant", event_type="QUEUE_CLEARED", zone_id=zone_id,
                                        timestamp=timestamp, severity="info",
                                        metadata={"peak_during_episode": peak}))
                level = "normal"

        self._queue_level[zone_id] = level
        return intents

    # ---------------------------------------------------------- idle staff
    def evaluate_idle_staff(self, track_id: int, zone_id: str, zone_type: str, role: str,
                             idle_duration: float, timestamp: float) -> list[dict]:
        intents = []
        key = f"idle:{track_id}:{zone_id}"
        threshold = self.thresholds["idle_staff_seconds"]
        eligible = zone_type == "PREP_ZONE" and role in ("STAFF", "UNKNOWN")
        is_open = key in self._idle_open

        if eligible and idle_duration >= threshold:
            if not is_open:
                intents.append(_intent("open", key=key, event_type="POTENTIAL_IDLE_STAFF", zone_id=zone_id,
                                        track_ids=[track_id], timestamp=timestamp - idle_duration,
                                        severity="warning", confidence=0.7,
                                        metadata={"idle_seconds_at_detection": round(idle_duration, 1)}))
                self._idle_open.add(key)
        elif is_open:
            intents.append(_intent("close", key=key, timestamp=timestamp))
            self._idle_open.discard(key)

        return intents

    # ---------------------------------------------------------- table clearing delay
    def evaluate_table(self, table_id: str, state: str, vacated_seconds_ago: float | None,
                        timestamp: float) -> list[dict]:
        intents = []
        key = f"table_clearing:{table_id}"
        is_open = key in self._table_open

        if state == "CLEARING_DELAY":
            if not is_open:
                start = timestamp - (vacated_seconds_ago or 0)
                intents.append(_intent("open", key=key, event_type="POTENTIAL_TABLE_CLEARING_DELAY",
                                        zone_id=table_id, timestamp=start, severity="warning", confidence=0.75,
                                        metadata={"vacated_seconds_ago": round(vacated_seconds_ago or 0, 1)}))
                self._table_open.add(key)
        elif is_open:
            intents.append(_intent("close", key=key, timestamp=timestamp))
            self._table_open.discard(key)

        return intents

    # ---------------------------------------------------------- pickup delay
    def evaluate_pickup(self, object_track_id: int, zone_id: str, dwell_seconds: float,
                         timestamp: float) -> list[dict]:
        intents = []
        key = f"pickup:{object_track_id}:{zone_id}"
        threshold = self.thresholds["pickup_delay_seconds"]
        is_open = key in self._pickup_open

        if dwell_seconds >= threshold:
            if not is_open:
                intents.append(_intent("open", key=key, event_type="POTENTIAL_PICKUP_DELAY", zone_id=zone_id,
                                        track_ids=[object_track_id], timestamp=timestamp - dwell_seconds,
                                        severity="warning", confidence=0.65,
                                        metadata={"note": "Potential unattended pickup item"}))
                self._pickup_open.add(key)
        elif is_open:
            intents.append(_intent("close", key=key, timestamp=timestamp))
            self._pickup_open.discard(key)

        return intents

    # ---------------------------------------------------------- queue abandonment
    def evaluate_abandonment(self, track_id: int, queue_dwell_seconds: float, reached_counter: bool,
                              timestamp: float) -> list[dict]:
        min_duration = self.thresholds["abandonment_min_queue_seconds"]
        if queue_dwell_seconds >= min_duration and not reached_counter:
            return [_intent("instant", event_type="POTENTIAL_QUEUE_ABANDONMENT", zone_id="QUEUE_ZONE",
                             track_ids=[track_id], timestamp=timestamp, severity="info", confidence=0.6,
                             metadata={"queue_dwell_seconds": round(queue_dwell_seconds, 1)})]
        return []

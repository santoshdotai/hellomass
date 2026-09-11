"""Layer 6 — RulesEngine: turns FrameAnalytics + source status changes into
EventCandidates. It knows nothing about OpenCV, the UI or SQLite."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Iterable

from src.analytics.spatial import FrameAnalytics
from src.rules.models import EventCandidate, Rule, RuleType, Schedule, Severity
from src.utils.time_utils import is_within_business_hours


class RulesEngine:
    def __init__(self, rules: Iterable[Rule], business_hours: dict | None = None, tz_name: str = "local",
                 clock: Callable[[], float] | None = None):
        self.rules: list[Rule] = list(rules)
        self.business_hours = business_hours or {"start": "08:00", "end": "18:00", "days": [0, 1, 2, 3, 4, 5]}
        self.tz_name = tz_name
        self._clock = clock
        self._last_fired: dict[tuple[str, str], float] = {}
        self.fired_total = 0

    # ---- configuration ---------------------------------------------------------
    def set_rules(self, rules: Iterable[Rule]) -> None:
        self.rules = list(rules)

    def set_business_hours(self, hours: dict) -> None:
        self.business_hours = dict(hours)

    def rules_of(self, rule_type: RuleType, source_id: str | None = None) -> list[Rule]:
        return [r for r in self.rules if r.enabled and r.rule_type == rule_type
                and (r.source_id in (None, "", source_id))]

    def rule(self, rule_type: RuleType) -> Rule | None:
        return next((r for r in self.rules if r.rule_type == rule_type), None)

    # ---- helpers ------------------------------------------------------------------
    def within_business_hours(self, ts: float) -> bool:
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        bh = self.business_hours
        return is_within_business_hours(dt, bh.get("start", "08:00"), bh.get("end", "18:00"),
                                        bh.get("days", [0, 1, 2, 3, 4, 5]), self.tz_name)

    def _schedule_allows(self, rule: Rule, ts: float) -> bool:
        s: Schedule = rule.schedule
        if s.mode == "within_hours":
            return self.within_business_hours(ts)
        if s.mode == "outside_hours":
            return not self.within_business_hours(ts)
        if s.mode == "window" and s.start and s.end:
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            return is_within_business_hours(dt, s.start, s.end, s.days or [0, 1, 2, 3, 4, 5, 6], self.tz_name)
        return True

    def _cooldown_ok(self, rule: Rule, scope: str, ts: float) -> bool:
        key = (rule.rule_id, scope)
        last = self._last_fired.get(key)
        if last is not None and rule.cooldown_seconds > 0 and ts - last < rule.cooldown_seconds:
            return False
        self._last_fired[key] = ts
        self.fired_total += 1
        return True

    def _zone_matches(self, rule: Rule, zone_id: str | None) -> bool:
        return rule.zone_id in (None, "") or rule.zone_id == zone_id

    def reset_cooldowns(self) -> None:
        self._last_fired.clear()

    # ---- evaluation ---------------------------------------------------------------
    def evaluate(self, fa: FrameAnalytics, source_id: str, source_name: str, media_time: float | None = None) -> list[EventCandidate]:
        out: list[EventCandidate] = []
        ts = fa.timestamp
        zones = fa.zones

        # 1. restricted-zone intrusion
        for rule in self.rules_of(RuleType.RESTRICTED_ZONE_INTRUSION, source_id):
            if not self._schedule_allows(rule, ts):
                continue
            for tr in fa.entered:
                if tr.zone_kind != "restricted" or not self._zone_matches(rule, tr.zone_id):
                    continue
                if self._cooldown_ok(rule, f"{tr.zone_id}:{tr.track_id}", ts):
                    out.append(EventCandidate(rule, rule.rule_type.value, f"Person {tr.track_id} entered restricted zone '{tr.zone_name}'",
                                              ts, rule.severity, source_id, source_name, tr.zone_id, tr.zone_name, tr.track_id,
                                              self._track_conf(fa, tr.track_id), {"zone_kind": tr.zone_kind}, media_time))

        # 2. dwell exceeded
        for rule in self.rules_of(RuleType.DWELL_TIME_EXCEEDED, source_id):
            if not self._schedule_allows(rule, ts):
                continue
            for da in fa.dwell_alerts:
                if not self._zone_matches(rule, da.zone_id):
                    continue
                if self._cooldown_ok(rule, f"{da.zone_id}:{da.track_id}", ts):
                    out.append(EventCandidate(rule, rule.rule_type.value,
                                              f"Person {da.track_id} stayed {da.dwell_seconds:.0f}s in '{da.zone_name}' (limit {da.threshold_seconds:.0f}s)",
                                              ts, rule.severity, source_id, source_name, da.zone_id, da.zone_name, da.track_id,
                                              self._track_conf(fa, da.track_id),
                                              {"dwell_seconds": round(da.dwell_seconds, 1), "threshold_seconds": da.threshold_seconds}, media_time))

        # 3/4. line crossings
        for cr in fa.crossings:
            rt = RuleType.LINE_CROSSED_IN if cr.direction == "in" else RuleType.LINE_CROSSED_OUT
            for rule in self.rules_of(rt, source_id):
                if not self._schedule_allows(rule, ts) or not self._zone_matches(rule, cr.zone_id):
                    continue
                if self._cooldown_ok(rule, f"{cr.zone_id}:{cr.track_id}", ts):
                    out.append(EventCandidate(rule, rt.value, f"{cr.label}: Person {cr.track_id} crossed '{cr.zone_name}' ({cr.direction})",
                                              ts, rule.severity, source_id, source_name, cr.zone_id, cr.zone_name, cr.track_id,
                                              self._track_conf(fa, cr.track_id), {"direction": cr.direction, "label": cr.label,
                                                                                  "entries": fa.entries, "exits": fa.exits}, media_time))

        # 5. occupancy threshold
        for rule in self.rules_of(RuleType.OCCUPANCY_THRESHOLD, source_id):
            if not self._schedule_allows(rule, ts):
                continue
            for zid, count in fa.zone_counts.items():
                zone = zones.get(zid)
                if zone is None or zone.kind != "occupancy" or not self._zone_matches(rule, zid):
                    continue
                limit = zone.occupancy_limit if zone.occupancy_limit else rule.threshold
                if limit is None or count <= int(limit):
                    self._last_fired.pop((rule.rule_id, zid), None)  # re-arm once occupancy drops back
                    continue
                if self._cooldown_ok(rule, zid, ts):
                    out.append(EventCandidate(rule, rule.rule_type.value, f"{count} people in '{zone.name}' (limit {int(limit)})",
                                              ts, rule.severity, source_id, source_name, zid, zone.name, None, None,
                                              {"count": count, "limit": int(limit)}, media_time))

        # 6. after-hours person
        for rule in self.rules_of(RuleType.AFTER_HOURS_PERSON, source_id):
            if fa.people_visible == 0 or self.within_business_hours(ts):
                continue
            if rule.schedule.mode not in ("always", "outside_hours"):
                continue
            # one alert per source per cooldown period (not per person) so a busy scene cannot flood the operator
            if self._cooldown_ok(rule, f"source:{source_id}", ts):
                tv = fa.tracks[0]
                out.append(EventCandidate(rule, rule.rule_type.value,
                                          f"{fa.people_visible} person(s) detected outside working hours (e.g. Person {tv.track_id})",
                                          ts, rule.severity, source_id, source_name, None, None, tv.track_id, tv.confidence,
                                          {"business_hours": self.business_hours, "people_visible": fa.people_visible,
                                           "track_ids": [t.track_id for t in fa.tracks]}, media_time))
        return out

    def on_source_status(self, old: str, new: str, source_id: str, source_name: str, ts: float,
                         detail: str = "") -> list[EventCandidate]:
        out = []
        if new == "disconnected" and old in ("live", "degraded", "connecting"):
            for rule in self.rules_of(RuleType.CAMERA_DISCONNECTED, source_id):
                if self._cooldown_ok(rule, source_id, ts):
                    out.append(EventCandidate(rule, rule.rule_type.value, f"Camera '{source_name}' disconnected", ts,
                                              rule.severity, source_id, source_name, None, None, None, None,
                                              {"previous_status": old, "detail": detail}, None))
        elif new == "live" and old in ("disconnected", "degraded"):
            for rule in self.rules_of(RuleType.CAMERA_RECONNECTED, source_id):
                if self._cooldown_ok(rule, source_id, ts):
                    out.append(EventCandidate(rule, rule.rule_type.value, f"Camera '{source_name}' reconnected", ts,
                                              rule.severity, source_id, source_name, None, None, None, None,
                                              {"previous_status": old}, None))
        return out

    @staticmethod
    def _track_conf(fa: FrameAnalytics, track_id: int) -> float | None:
        for tv in fa.tracks:
            if tv.track_id == track_id:
                return tv.confidence
        return None

    def summary(self) -> dict:
        return {"rules": len(self.rules), "enabled": sum(1 for r in self.rules if r.enabled), "fired_total": self.fired_total}


__all__ = ["RulesEngine", "Severity", "Rule", "RuleType", "EventCandidate"]

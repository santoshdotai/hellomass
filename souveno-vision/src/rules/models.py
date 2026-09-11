"""Layer 6 — rule and event-candidate models. Plain dataclasses only, so the
rules engine stays independent of the UI, the detector and the database."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class RuleType(str, Enum):
    RESTRICTED_ZONE_INTRUSION = "restricted_zone_intrusion"
    DWELL_TIME_EXCEEDED = "dwell_time_exceeded"
    LINE_CROSSED_IN = "line_crossed_in"
    LINE_CROSSED_OUT = "line_crossed_out"
    OCCUPANCY_THRESHOLD = "occupancy_threshold"
    AFTER_HOURS_PERSON = "after_hours_person"
    CAMERA_DISCONNECTED = "camera_disconnected"
    CAMERA_RECONNECTED = "camera_reconnected"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


SEVERITY_ORDER = {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2, Severity.CRITICAL: 3}

RULE_TITLES = {
    RuleType.RESTRICTED_ZONE_INTRUSION: "Restricted zone intrusion",
    RuleType.DWELL_TIME_EXCEEDED: "Dwell time exceeded",
    RuleType.LINE_CROSSED_IN: "Line crossed inward",
    RuleType.LINE_CROSSED_OUT: "Line crossed outward",
    RuleType.OCCUPANCY_THRESHOLD: "Occupancy threshold exceeded",
    RuleType.AFTER_HOURS_PERSON: "Person detected after hours",
    RuleType.CAMERA_DISCONNECTED: "Camera disconnected",
    RuleType.CAMERA_RECONNECTED: "Camera reconnected",
}

RULE_DESCRIPTIONS = {
    RuleType.RESTRICTED_ZONE_INTRUSION: "A tracked person's foot point entered a zone of kind 'restricted'.",
    RuleType.DWELL_TIME_EXCEEDED: "A person stayed inside a zone longer than the threshold (zone override or rule default).",
    RuleType.LINE_CROSSED_IN: "A person crossed a virtual line in the 'in' direction.",
    RuleType.LINE_CROSSED_OUT: "A person crossed a virtual line in the 'out' direction.",
    RuleType.OCCUPANCY_THRESHOLD: "The number of people inside an occupancy zone exceeded its limit.",
    RuleType.AFTER_HOURS_PERSON: "A person was detected outside the configured working hours.",
    RuleType.CAMERA_DISCONNECTED: "The video source stopped delivering frames.",
    RuleType.CAMERA_RECONNECTED: "The video source recovered after a disconnection.",
}


@dataclass
class Schedule:
    """When a rule is armed. mode: always | within_hours | outside_hours (relative to business hours)."""
    mode: str = "always"
    start: str | None = None      # optional explicit window, "HH:MM"
    end: str | None = None
    days: list[int] | None = None  # 0=Mon .. 6=Sun

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Rule:
    rule_type: RuleType
    name: str = ""
    enabled: bool = True
    source_id: str | None = None        # None = every source
    zone_id: str | None = None          # None = every applicable zone
    threshold: float | None = None      # seconds for dwell, count for occupancy
    schedule: Schedule = field(default_factory=Schedule)
    severity: Severity = Severity.MEDIUM
    cooldown_seconds: float = 30.0
    evidence_required: bool = True
    notify: bool = False
    rule_id: str = field(default_factory=lambda: f"R-{uuid.uuid4().hex[:8].upper()}")

    def __post_init__(self):
        self.rule_type = RuleType(self.rule_type)
        self.severity = Severity(self.severity)
        if isinstance(self.schedule, dict):
            self.schedule = Schedule(**self.schedule)
        if not self.name:
            self.name = RULE_TITLES[self.rule_type]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["rule_type"] = self.rule_type.value
        d["severity"] = self.severity.value
        d["title"] = RULE_TITLES[self.rule_type]
        d["description"] = RULE_DESCRIPTIONS[self.rule_type]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Rule":
        allowed = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in d.items() if k in allowed})


@dataclass
class EventCandidate:
    rule: Rule
    event_type: str
    title: str
    timestamp: float                 # wall clock seconds
    severity: Severity
    source_id: str = ""
    source_name: str = ""
    zone_id: str | None = None
    zone_name: str | None = None
    track_id: int | None = None
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    media_time: float | None = None

    @property
    def evidence_required(self) -> bool:
        return self.rule.evidence_required

    @property
    def notify(self) -> bool:
        return self.rule.notify


# Built-in defaults (mirrors config/default.yaml) used when a rule is missing from the config.
BUILTIN_RULE_DEFAULTS: dict[str, dict] = {
    "restricted_zone_intrusion": {"enabled": True, "severity": "high", "cooldown_seconds": 20, "evidence": True, "notify": True},
    "dwell_time_exceeded": {"enabled": True, "severity": "medium", "cooldown_seconds": 30, "evidence": True, "notify": True, "threshold_seconds": 10},
    "line_crossed_in": {"enabled": True, "severity": "low", "cooldown_seconds": 0, "evidence": False, "notify": False},
    "line_crossed_out": {"enabled": True, "severity": "low", "cooldown_seconds": 0, "evidence": False, "notify": False},
    "occupancy_threshold": {"enabled": True, "severity": "medium", "cooldown_seconds": 60, "evidence": True, "notify": True, "threshold": 5},
    "after_hours_person": {"enabled": True, "severity": "high", "cooldown_seconds": 120, "evidence": True, "notify": True},
    "camera_disconnected": {"enabled": True, "severity": "critical", "cooldown_seconds": 30, "evidence": False, "notify": True},
    "camera_reconnected": {"enabled": True, "severity": "low", "cooldown_seconds": 0, "evidence": False, "notify": True},
}


def default_rules(rules_cfg: dict | None = None) -> list[Rule]:
    """Factory defaults from config/default.yaml `rules:` section (built-in fallback per rule)."""
    cfg = rules_cfg or {}
    rules = []
    for rt in RuleType:
        c = {**BUILTIN_RULE_DEFAULTS.get(rt.value, {}), **(cfg.get(rt.value, {}) or {})}
        threshold = c.get("threshold_seconds", c.get("threshold"))
        rules.append(Rule(rule_type=rt, enabled=bool(c.get("enabled", True)), threshold=threshold,
                          severity=Severity(c.get("severity", "medium")), cooldown_seconds=float(c.get("cooldown_seconds", 30)),
                          evidence_required=bool(c.get("evidence", True)), notify=bool(c.get("notify", False)),
                          rule_id=f"R-{rt.value.upper()[:18]}"))
    return rules

from datetime import datetime, timezone

from src.analytics.dwell import DwellAlert
from src.analytics.line_crossing import Crossing
from src.analytics.occupancy import ZoneTransition
from src.analytics.spatial import FrameAnalytics, TrackView
from src.analytics.zones import Zone
from src.rules.engine import RulesEngine
from src.rules.models import Rule, RuleType, Severity, default_rules

RESTRICTED = Zone(name="Bay", kind="restricted", points=[[0.5, 0], [1, 0], [1, 1], [0.5, 1]])
HALL = Zone(name="Hall", kind="occupancy", points=[[0, 0], [0.5, 0], [0.5, 1], [0, 1]], occupancy_limit=2)
DOOR = Zone(name="Door", kind="line", points=[[0.5, 0], [0.5, 1]])
ZONES = {z.zone_id: z for z in (RESTRICTED, HALL, DOOR)}
WORKDAY_NOON = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc).timestamp()   # Wednesday
NIGHT = datetime(2026, 9, 9, 23, 0, tzinfo=timezone.utc).timestamp()
HOURS = {"start": "08:00", "end": "18:00", "days": [0, 1, 2, 3, 4]}


def fa(ts, tracks=1, entered=(), crossings=(), dwell=(), counts=None):
    views = [TrackView(i + 1, (0, 0, 10, 10), 0.9, [], [], {}, False, []) for i in range(tracks)]
    return FrameAnalytics(ts, views, list(entered), [], list(crossings), list(dwell), counts or {}, {}, tracks, 0, 0, tracks, ZONES)


def engine(**over):
    rules = default_rules()
    for r in rules:
        for k, v in over.items():
            setattr(r, k, v)
    return RulesEngine(rules, HOURS, tz_name="UTC")


def test_restricted_intrusion_and_cooldown():
    e = engine(cooldown_seconds=10)
    tr = ZoneTransition(RESTRICTED.zone_id, "Bay", "restricted", 7, WORKDAY_NOON)
    out = e.evaluate(fa(WORKDAY_NOON, entered=[tr]), "cam1", "Cam 1")
    assert [c.event_type for c in out] == [RuleType.RESTRICTED_ZONE_INTRUSION.value]
    assert out[0].track_id == 7 and out[0].zone_name == "Bay" and out[0].severity == Severity.HIGH
    # same track again within cooldown: suppressed; other track: allowed
    assert e.evaluate(fa(WORKDAY_NOON + 5, entered=[tr]), "cam1", "Cam 1") == []
    tr2 = ZoneTransition(RESTRICTED.zone_id, "Bay", "restricted", 8, WORKDAY_NOON + 5)
    assert len(e.evaluate(fa(WORKDAY_NOON + 5, entered=[tr2]), "cam1", "Cam 1")) == 1
    assert len(e.evaluate(fa(WORKDAY_NOON + 11, entered=[tr]), "cam1", "Cam 1")) == 1


def test_disabled_rule_never_fires():
    e = engine()
    e.rule(RuleType.RESTRICTED_ZONE_INTRUSION).enabled = False
    tr = ZoneTransition(RESTRICTED.zone_id, "Bay", "restricted", 7, WORKDAY_NOON)
    assert e.evaluate(fa(WORKDAY_NOON, entered=[tr]), "cam1", "Cam 1") == []


def test_dwell_rule():
    e = engine()
    da = DwellAlert(RESTRICTED.zone_id, "Bay", 3, 12.0, 10.0, WORKDAY_NOON)
    out = e.evaluate(fa(WORKDAY_NOON, dwell=[da]), "cam1", "Cam 1")
    assert out[0].event_type == "dwell_time_exceeded" and out[0].metadata["dwell_seconds"] == 12.0


def test_line_crossings_map_to_in_and_out_rules():
    e = engine()
    cr_in = Crossing(DOOR.zone_id, "Door", 1, "in", "Entry", WORKDAY_NOON)
    cr_out = Crossing(DOOR.zone_id, "Door", 2, "out", "Exit", WORKDAY_NOON)
    out = e.evaluate(fa(WORKDAY_NOON, tracks=2, crossings=[cr_in, cr_out]), "cam1", "Cam 1")
    assert sorted(c.event_type for c in out) == ["line_crossed_in", "line_crossed_out"]


def test_occupancy_threshold_rising_edge_and_rearm():
    e = engine(cooldown_seconds=60)
    over = {HALL.zone_id: 3}
    assert len(e.evaluate(fa(WORKDAY_NOON, tracks=3, counts=over), "cam1", "Cam 1")) == 1
    assert e.evaluate(fa(WORKDAY_NOON + 1, tracks=3, counts=over), "cam1", "Cam 1") == []      # cooldown
    assert e.evaluate(fa(WORKDAY_NOON + 2, tracks=2, counts={HALL.zone_id: 2}), "cam1", "Cam 1") == []  # at limit, re-arms
    assert len(e.evaluate(fa(WORKDAY_NOON + 3, tracks=3, counts=over), "cam1", "Cam 1")) == 1


def test_after_hours_detection_once_per_source():
    e = engine(cooldown_seconds=120)
    assert e.evaluate(fa(WORKDAY_NOON, tracks=2), "cam1", "Cam 1") == []       # inside business hours
    out = e.evaluate(fa(NIGHT, tracks=2), "cam1", "Cam 1")
    assert len(out) == 1 and out[0].event_type == "after_hours_person" and out[0].metadata["people_visible"] == 2
    assert e.evaluate(fa(NIGHT + 30, tracks=5), "cam1", "Cam 1") == []       # cooldown per source
    assert len(e.evaluate(fa(NIGHT + 121, tracks=1), "cam1", "Cam 1")) == 1
    assert e.evaluate(fa(NIGHT + 200, tracks=0), "cam1", "Cam 1") == []      # nobody there


def test_schedule_outside_hours_gates_intrusion():
    e = engine()
    r = e.rule(RuleType.RESTRICTED_ZONE_INTRUSION)
    r.schedule.mode = "outside_hours"
    tr = ZoneTransition(RESTRICTED.zone_id, "Bay", "restricted", 7, WORKDAY_NOON)
    assert e.evaluate(fa(WORKDAY_NOON, entered=[tr]), "cam1", "Cam 1") == []
    tr_night = ZoneTransition(RESTRICTED.zone_id, "Bay", "restricted", 7, NIGHT)
    night = e.evaluate(fa(NIGHT, entered=[tr_night]), "cam1", "Cam 1")
    assert [c.event_type for c in night if c.event_type == "restricted_zone_intrusion"] == ["restricted_zone_intrusion"]


def test_camera_disconnect_and_reconnect_events():
    e = engine()
    out = e.on_source_status("live", "disconnected", "cam1", "Cam 1", WORKDAY_NOON, "timeout")
    assert out[0].event_type == "camera_disconnected" and out[0].severity == Severity.CRITICAL
    out = e.on_source_status("disconnected", "live", "cam1", "Cam 1", WORKDAY_NOON + 5)
    assert out[0].event_type == "camera_reconnected"
    assert e.on_source_status("idle", "connecting", "cam1", "Cam 1", WORKDAY_NOON) == []


def test_rule_source_scoping():
    e = engine()
    e.rule(RuleType.RESTRICTED_ZONE_INTRUSION).source_id = "cam2"
    tr = ZoneTransition(RESTRICTED.zone_id, "Bay", "restricted", 7, WORKDAY_NOON)
    assert e.evaluate(fa(WORKDAY_NOON, entered=[tr]), "cam1", "Cam 1") == []
    assert len(e.evaluate(fa(WORKDAY_NOON, entered=[tr]), "cam2", "Cam 2")) == 1


def test_rule_roundtrip_dict():
    r = Rule(rule_type="dwell_time_exceeded", severity="critical", threshold=42, schedule={"mode": "within_hours"})
    d = r.to_dict()
    r2 = Rule.from_dict(d)
    assert r2.rule_type == RuleType.DWELL_TIME_EXCEEDED and r2.severity == Severity.CRITICAL and r2.schedule.mode == "within_hours"

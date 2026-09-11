from backend.core.zones import ZoneDef, ZoneEngine

QUEUE = ZoneDef(zone_id="Queue", name="Queue", zone_type="QUEUE_ZONE", shape_type="polygon",
                 points=[(0.0, 0.0), (0.5, 0.0), (0.5, 1.0), (0.0, 1.0)])
COUNTER = ZoneDef(zone_id="Counter", name="Counter", zone_type="COUNTER_ZONE", shape_type="polygon",
                   points=[(0.5, 0.0), (1.0, 0.0), (1.0, 1.0), (0.5, 1.0)])
ENTRANCE = ZoneDef(zone_id="Entrance", name="Entrance", zone_type="ENTRANCE_LINE", shape_type="line",
                    points=[(0.0, 0.5), (1.0, 0.5)])


def test_zone_enter_and_exit_detected():
    engine = ZoneEngine([QUEUE, COUNTER])
    r1 = engine.update(1, (0.25, 0.5), timestamp=0.0)
    assert r1.zones_entered == ["Queue"]

    r2 = engine.update(1, (0.75, 0.5), timestamp=5.0)
    assert r2.zones_exited == ["Queue"]
    assert r2.zones_entered == ["Counter"]


def test_dwell_seconds_accumulates_while_inside():
    engine = ZoneEngine([QUEUE])
    engine.update(1, (0.25, 0.5), timestamp=0.0)
    engine.update(1, (0.25, 0.5), timestamp=10.0)
    assert engine.dwell_seconds(1, "Queue", timestamp=10.0) == 10.0


def test_dwell_resets_after_leaving_and_reentering():
    engine = ZoneEngine([QUEUE, COUNTER])
    engine.update(1, (0.25, 0.5), timestamp=0.0)
    engine.update(1, (0.75, 0.5), timestamp=5.0)  # left queue
    engine.update(1, (0.25, 0.5), timestamp=8.0)  # re-entered queue
    assert engine.dwell_seconds(1, "Queue", timestamp=9.0) == 1.0


def test_line_crossing_direction_reported():
    engine = ZoneEngine([ENTRANCE])
    engine.update(1, (0.5, 0.2), timestamp=0.0)
    result = engine.update(1, (0.5, 0.8), timestamp=1.0)
    assert len(result.line_crossings) == 1
    assert result.line_crossings[0]["zone_id"] == "Entrance"


def test_forget_track_clears_state():
    engine = ZoneEngine([QUEUE])
    engine.update(1, (0.25, 0.5), timestamp=0.0)
    engine.forget_track(1)
    assert engine.dwell_seconds(1, "Queue", timestamp=5.0) == 0.0
    occupants = engine.zone_occupants()
    assert 1 not in occupants.get("Queue", set())

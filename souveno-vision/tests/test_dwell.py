from src.analytics.dwell import DwellTracker
from src.analytics.occupancy import ZoneOccupancy
from src.analytics.zones import Zone

RESTRICTED = Zone(name="Bay", kind="restricted", points=[[0.5, 0.0], [1.0, 0.0], [1.0, 1.0], [0.5, 1.0]])
COUNT_ZONE = Zone(name="Hall", kind="occupancy", points=[[0.0, 0.0], [0.5, 0.0], [0.5, 1.0], [0.0, 1.0]])


def make(threshold=5.0, enter=1, exit=1, zones=None):
    occ = ZoneOccupancy(zones or [RESTRICTED, COUNT_ZONE], enter_frames=enter, exit_frames=exit)
    return occ, DwellTracker(occ, default_threshold_seconds=threshold)


def test_dwell_alert_fires_once_per_visit():
    occ, dw = make(threshold=5.0)
    inside = occ.update(1, (0.75, 0.5), 0.0).inside
    assert dw.evaluate(1, inside, 0.0) == []
    inside = occ.update(1, (0.75, 0.5), 4.9).inside
    assert dw.evaluate(1, inside, 4.9) == []
    inside = occ.update(1, (0.75, 0.5), 5.0).inside
    alerts = dw.evaluate(1, inside, 5.0)
    assert len(alerts) == 1 and alerts[0].dwell_seconds == 5.0 and alerts[0].zone_name == "Bay"
    inside = occ.update(1, (0.75, 0.5), 9.0).inside
    assert dw.evaluate(1, inside, 9.0) == []  # not repeated while still inside


def test_dwell_resets_after_exit_and_reentry():
    occ, dw = make(threshold=2.0)
    occ.update(1, (0.75, 0.5), 0.0)
    dw.evaluate(1, occ.update(1, (0.75, 0.5), 2.0).inside, 2.0)
    ex = occ.update(1, (0.25, 0.5), 3.0)
    assert ex.exited and ex.exited[0].zone_name == "Bay"
    dw.on_exit(1, RESTRICTED.zone_id, 3.0)
    occ.update(1, (0.75, 0.5), 4.0)
    assert dw.evaluate(1, occ.update(1, (0.75, 0.5), 5.0).inside, 5.0) == []
    assert len(dw.evaluate(1, occ.update(1, (0.75, 0.5), 6.0).inside, 6.0)) == 1


def test_zone_specific_threshold_overrides_default():
    z = Zone(name="Bay", kind="restricted", points=RESTRICTED.points, dwell_threshold_seconds=1.0)
    occ, dw = make(threshold=30.0, zones=[z])
    occ.update(1, (0.75, 0.5), 0.0)
    assert len(dw.evaluate(1, occ.update(1, (0.75, 0.5), 1.0).inside, 1.0)) == 1


def test_occupancy_zone_has_no_dwell_alert_by_default():
    occ, dw = make(threshold=1.0)
    occ.update(1, (0.25, 0.5), 0.0)
    assert dw.evaluate(1, occ.update(1, (0.25, 0.5), 10.0).inside, 10.0) == []


def test_hysteresis_prevents_enter_exit_storms():
    occ = ZoneOccupancy([RESTRICTED], enter_frames=2, exit_frames=3)
    assert occ.update(1, (0.75, 0.5), 0.0).entered == []      # first frame inside: not yet confirmed
    assert len(occ.update(1, (0.75, 0.5), 0.1).entered) == 1  # second frame: confirmed
    assert occ.update(1, (0.49, 0.5), 0.2).exited == []       # one frame outside: still inside
    assert occ.update(1, (0.51, 0.5), 0.3).exited == []
    assert occ.update(1, (0.49, 0.5), 0.4).exited == []
    assert occ.update(1, (0.49, 0.5), 0.5).exited == []
    assert len(occ.update(1, (0.49, 0.5), 0.6).exited) == 1   # third consecutive frame outside


def test_average_dwell_statistics():
    occ, dw = make(threshold=100)
    occ.update(1, (0.75, 0.5), 0.0)
    dw.on_exit(1, RESTRICTED.zone_id, 10.0)
    dw.on_exit(2, RESTRICTED.zone_id, 20.0)
    assert dw.average_dwell(RESTRICTED.zone_id) == 15.0
    assert occ.counts()[RESTRICTED.zone_id] == 1

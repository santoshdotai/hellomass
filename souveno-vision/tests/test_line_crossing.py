from src.analytics.line_crossing import LineCrossingCounter
from src.analytics.zones import Zone

VERTICAL = Zone(name="Door", kind="line", points=[[0.5, 0.0], [0.5, 1.0]])


def make(debounce=1.0, margin=0.004, flipped=False):
    z = Zone(name="Door", kind="line", points=[[0.5, 0.0], [0.5, 1.0]], direction_flipped=flipped)
    return LineCrossingCounter([z], debounce_seconds=debounce, side_margin=margin), z


def test_directional_counting():
    lc, z = make()
    assert lc.update(1, (0.2, 0.5), 0.0) == []
    crossings = lc.update(1, (0.8, 0.5), 1.0)
    assert len(crossings) == 1
    d1 = crossings[0].direction
    back = lc.update(1, (0.2, 0.5), 3.0)
    assert len(back) == 1 and back[0].direction != d1
    assert lc.counts[z.zone_id]["in"] == 1 and lc.counts[z.zone_id]["out"] == 1


def test_flip_swaps_direction():
    lc1, _ = make(); lc2, _ = make(flipped=True)
    lc1.update(1, (0.2, 0.5), 0.0); lc2.update(1, (0.2, 0.5), 0.0)
    d1 = lc1.update(1, (0.8, 0.5), 1.0)[0].direction
    d2 = lc2.update(1, (0.8, 0.5), 1.0)[0].direction
    assert d1 != d2


def test_boundary_jitter_is_not_counted():
    lc, z = make(margin=0.01)
    lc.update(1, (0.3, 0.5), 0.0)
    # wobble right on the line for several frames: undecided side, no crossings
    for i, x in enumerate([0.499, 0.501, 0.498, 0.502, 0.5]):
        assert lc.update(1, (x, 0.5), 0.1 * (i + 1)) == []
    assert lc.totals() == {"in": 0, "out": 0}
    # then a real crossing
    assert len(lc.update(1, (0.7, 0.5), 2.0)) == 1


def test_debounce_blocks_rapid_repeat_crossings():
    lc, _ = make(debounce=2.0)
    lc.update(1, (0.2, 0.5), 0.0)
    assert len(lc.update(1, (0.8, 0.5), 0.5)) == 1
    assert len(lc.update(1, (0.2, 0.5), 0.9)) == 0   # within debounce window: ignored
    assert len(lc.update(1, (0.8, 0.5), 3.5)) == 1   # after the window: counted


def test_movement_past_line_endpoints_does_not_count():
    z = Zone(name="Short", kind="line", points=[[0.5, 0.4], [0.5, 0.6]])
    lc = LineCrossingCounter([z], debounce_seconds=0.0)
    lc.update(1, (0.2, 0.9), 0.0)
    assert lc.update(1, (0.8, 0.9), 1.0) == []


def test_forget_and_reset():
    lc, z = make()
    lc.update(1, (0.2, 0.5), 0.0); lc.update(1, (0.8, 0.5), 1.0)
    lc.forget(1)
    lc.reset_counts()
    assert lc.totals() == {"in": 0, "out": 0}
    assert lc.update(1, (0.2, 0.5), 5.0) == []  # side is re-learned after forget

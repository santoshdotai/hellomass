from backend.core.activity import ActivityEngine


def test_stationary_track_reports_growing_idle_duration():
    engine = ActivityEngine(motion_threshold=0.02, window_seconds=3.0)
    engine.update(1, (0.5, 0.5), timestamp=0.0)
    result = engine.update(1, (0.5, 0.5), timestamp=10.0)
    assert result["is_moving"] is False
    assert result["idle_duration"] == 10.0


def test_moving_track_resets_idle_duration():
    engine = ActivityEngine(motion_threshold=0.02, window_seconds=3.0)
    engine.update(1, (0.1, 0.1), timestamp=0.0)
    engine.update(1, (0.1, 0.1), timestamp=5.0)
    result = engine.update(1, (0.9, 0.9), timestamp=6.0)  # big jump = movement
    assert result["is_moving"] is True
    assert result["idle_duration"] == 0.0


def test_idle_duration_via_helper():
    engine = ActivityEngine()
    engine.update(1, (0.5, 0.5), timestamp=0.0)
    assert engine.idle_duration(1, timestamp=20.0) == 20.0
    assert engine.idle_duration(999, timestamp=20.0) == 0.0

from backend.core.tables import TableState, TableTracker


def test_table_starts_available():
    tracker = TableTracker(clearing_delay_seconds=30)
    status = tracker.update("T1", occupancy_count=0, timestamp=0.0)
    assert status.state == TableState.AVAILABLE


def test_table_occupied_then_vacated_then_clearing_delay():
    tracker = TableTracker(clearing_delay_seconds=30)
    assert tracker.update("T1", 2, timestamp=0.0).state == TableState.OCCUPIED
    vacated = tracker.update("T1", 0, timestamp=10.0)
    assert vacated.state == TableState.VACATED
    assert vacated.vacated_seconds_ago == 0.0

    still_vacated = tracker.update("T1", 0, timestamp=20.0)
    assert still_vacated.state == TableState.VACATED

    delayed = tracker.update("T1", 0, timestamp=45.0)
    assert delayed.state == TableState.CLEARING_DELAY
    assert delayed.vacated_seconds_ago == 35.0


def test_new_customers_reoccupy_from_clearing_delay():
    tracker = TableTracker(clearing_delay_seconds=10)
    tracker.update("T1", 1, timestamp=0.0)
    tracker.update("T1", 0, timestamp=1.0)
    tracker.update("T1", 0, timestamp=15.0)  # now CLEARING_DELAY
    reoccupied = tracker.update("T1", 2, timestamp=20.0)
    assert reoccupied.state == TableState.OCCUPIED

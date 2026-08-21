from backend.core.rules import RuleEngine

THRESHOLDS = {
    "queue_warning_count": 4,
    "queue_critical_count": 7,
    "queue_min_duration_seconds": 5,
    "idle_staff_seconds": 20,
    "table_clearing_delay_seconds": 30,
    "pickup_delay_seconds": 20,
    "abandonment_min_queue_seconds": 10,
}


def test_queue_warning_then_critical_then_cleared():
    engine = RuleEngine(THRESHOLDS)

    intents = engine.evaluate_queue("Queue", count=5, peak=5, timestamp=0.0)
    assert any(i["action"] == "open" and i["event_type"] == "QUEUE_WARNING" for i in intents)

    intents = engine.evaluate_queue("Queue", count=8, peak=8, timestamp=5.0)
    assert any(i["event_type"] == "QUEUE_CRITICAL" and i["action"] == "open" for i in intents)
    assert any(i["action"] == "close" and i["key"] == "queue_warning:Queue" for i in intents)

    intents = engine.evaluate_queue("Queue", count=1, peak=8, timestamp=10.0)
    assert any(i["event_type"] == "QUEUE_CLEARED" for i in intents)
    assert any(i["action"] == "close" and i["key"] == "queue_critical:Queue" for i in intents)


def test_queue_no_duplicate_open_while_still_warning():
    engine = RuleEngine(THRESHOLDS)
    engine.evaluate_queue("Queue", count=5, peak=5, timestamp=0.0)
    intents = engine.evaluate_queue("Queue", count=6, peak=6, timestamp=1.0)
    assert intents == []


def test_idle_staff_opens_after_threshold_and_closes_on_movement():
    engine = RuleEngine(THRESHOLDS)

    intents = engine.evaluate_idle_staff(7, "Prep", "PREP_ZONE", "STAFF", idle_duration=5, timestamp=5.0)
    assert intents == []  # below threshold

    intents = engine.evaluate_idle_staff(7, "Prep", "PREP_ZONE", "STAFF", idle_duration=25, timestamp=25.0)
    assert len(intents) == 1
    assert intents[0]["event_type"] == "POTENTIAL_IDLE_STAFF"
    assert intents[0]["action"] == "open"

    intents = engine.evaluate_idle_staff(7, "Prep", "PREP_ZONE", "STAFF", idle_duration=0, timestamp=26.0)
    assert len(intents) == 1
    assert intents[0]["action"] == "close"


def test_idle_staff_ignored_outside_prep_zone():
    engine = RuleEngine(THRESHOLDS)
    intents = engine.evaluate_idle_staff(7, "Dining", "DINING_ZONE", "CUSTOMER", idle_duration=100, timestamp=100.0)
    assert intents == []


def test_table_clearing_delay_open_and_close():
    engine = RuleEngine(THRESHOLDS)
    intents = engine.evaluate_table("T1", "VACATED", vacated_seconds_ago=5, timestamp=5.0)
    assert intents == []

    intents = engine.evaluate_table("T1", "CLEARING_DELAY", vacated_seconds_ago=35, timestamp=35.0)
    assert intents[0]["event_type"] == "POTENTIAL_TABLE_CLEARING_DELAY"
    assert intents[0]["action"] == "open"

    intents = engine.evaluate_table("T1", "OCCUPIED", vacated_seconds_ago=None, timestamp=50.0)
    assert intents[0]["action"] == "close"


def test_abandonment_only_fires_when_counter_not_reached():
    engine = RuleEngine(THRESHOLDS)
    intents = engine.evaluate_abandonment(3, queue_dwell_seconds=15, reached_counter=True, timestamp=15.0)
    assert intents == []

    intents = engine.evaluate_abandonment(3, queue_dwell_seconds=15, reached_counter=False, timestamp=15.0)
    assert len(intents) == 1
    assert intents[0]["event_type"] == "POTENTIAL_QUEUE_ABANDONMENT"

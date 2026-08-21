"""
Rule Engine configuration (Phase 15).

Rules are data, not code. Each rule can be toggled/edited from the UI
(persisted in the `settings` DB table) — this module only supplies the
factory defaults and the demo-vs-production threshold split.
"""
from config.settings import settings

# Demo-mode thresholds are intentionally short so a 2-5 minute recorded
# clip can still produce a full range of events. Production thresholds
# are what a real deployment should use.
DEMO_THRESHOLDS = {
    "queue_warning_count": 4,
    "queue_critical_count": 7,
    "queue_min_duration_seconds": 8,
    "idle_staff_seconds": 25,
    "table_clearing_delay_seconds": 30,
    "pickup_delay_seconds": 25,
    "abandonment_min_queue_seconds": 10,
}

PRODUCTION_THRESHOLDS = {
    "queue_warning_count": 4,
    "queue_critical_count": 7,
    "queue_min_duration_seconds": 15,
    "idle_staff_seconds": 600,       # 10 minutes
    "table_clearing_delay_seconds": 600,  # 10 minutes
    "pickup_delay_seconds": 300,     # 5 minutes
    "abandonment_min_queue_seconds": 30,
}


def get_active_thresholds() -> dict:
    return DEMO_THRESHOLDS.copy() if settings.demo_mode else PRODUCTION_THRESHOLDS.copy()


DEFAULT_RULES = [
    {
        "rule_name": "Queue Warning",
        "event_type": "QUEUE_WARNING",
        "zone_type": "QUEUE_ZONE",
        "threshold_key": "queue_warning_count",
        "severity": "warning",
        "enabled": True,
    },
    {
        "rule_name": "Queue Critical",
        "event_type": "QUEUE_CRITICAL",
        "zone_type": "QUEUE_ZONE",
        "threshold_key": "queue_critical_count",
        "severity": "critical",
        "enabled": True,
    },
    {
        "rule_name": "Prep Idle Warning",
        "event_type": "POTENTIAL_IDLE_STAFF",
        "zone_type": "PREP_ZONE",
        "threshold_key": "idle_staff_seconds",
        "severity": "warning",
        "enabled": True,
    },
    {
        "rule_name": "Table Clearing Delay",
        "event_type": "POTENTIAL_TABLE_CLEARING_DELAY",
        "zone_type": "TABLE",
        "threshold_key": "table_clearing_delay_seconds",
        "severity": "warning",
        "enabled": True,
    },
    {
        "rule_name": "Pickup Delay",
        "event_type": "POTENTIAL_PICKUP_DELAY",
        "zone_type": "PICKUP_ZONE",
        "threshold_key": "pickup_delay_seconds",
        "severity": "warning",
        "enabled": True,
    },
    {
        "rule_name": "Queue Abandonment",
        "event_type": "POTENTIAL_QUEUE_ABANDONMENT",
        "zone_type": "QUEUE_ZONE",
        "threshold_key": "abandonment_min_queue_seconds",
        "severity": "info",
        "enabled": True,
    },
]

ZONE_TYPES = [
    "COUNTER_ZONE",
    "QUEUE_ZONE",
    "DINING_ZONE",
    "PREP_ZONE",
    "PICKUP_ZONE",
    "ENTRANCE_LINE",
    "TABLE",
]

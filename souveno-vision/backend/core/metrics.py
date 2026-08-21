"""Metrics Aggregator (Phase 17) — turns the frame-by-frame stream of
zone/rule signals into the numbers shown on the live dashboard and the
end-of-video AI summary."""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field


@dataclass
class MetricsAggregator:
    peak_people: int = 0
    peak_queue: int = 0
    footfall_in: int = 0
    footfall_out: int = 0
    queue_dwell_samples: list = field(default_factory=list)
    idle_events_count: int = 0
    idle_durations: list = field(default_factory=list)
    abandonments: int = 0
    clearing_delay_events: int = 0
    pickup_delay_events: int = 0
    spill_events: int = 0

    _live: dict = field(default_factory=dict)

    # ---- event-driven counters -------------------------------------------------
    def record_footfall(self, direction: str):
        if direction == "enter":
            self.footfall_in += 1
        else:
            self.footfall_out += 1

    def record_queue_dwell(self, seconds: float):
        if seconds > 0:
            self.queue_dwell_samples.append(seconds)

    def record_idle_opened(self):
        self.idle_events_count += 1

    def record_idle_closed(self, duration_seconds: float):
        self.idle_durations.append(duration_seconds)

    def record_abandonment(self):
        self.abandonments += 1

    def record_clearing_delay(self):
        self.clearing_delay_events += 1

    def record_pickup_delay(self):
        self.pickup_delay_events += 1

    def record_spill(self):
        self.spill_events += 1

    # ---- per-frame snapshot ----------------------------------------------------
    def update_live(self, people_visible: int, zone_counts: dict[str, int], active_tracks: int,
                     queue_count: int, tables_status: dict, prep_staff_count: int,
                     potential_idle_staff_now: int, current_occupancy: int):
        self.peak_people = max(self.peak_people, people_visible)
        self.peak_queue = max(self.peak_queue, queue_count)
        tables_occupied = sum(1 for t in tables_status.values() if t.state.value == "OCCUPIED")
        tables_available = sum(1 for t in tables_status.values() if t.state.value == "AVAILABLE")
        self._live = {
            "people_visible": people_visible,
            "zone_counts": zone_counts,
            "active_tracks": active_tracks,
            "queue_length": queue_count,
            "tables_occupied": tables_occupied,
            "tables_available": tables_available,
            "prep_staff_count": prep_staff_count,
            "potential_idle_staff_now": potential_idle_staff_now,
            "current_occupancy": current_occupancy,
        }

    @staticmethod
    def _percentile(data: list, pct: float) -> float:
        if not data:
            return 0.0
        data = sorted(data)
        k = (len(data) - 1) * pct
        f = int(k)
        c = min(f + 1, len(data) - 1)
        if f == c:
            return data[f]
        return data[f] + (data[c] - data[f]) * (k - f)

    def snapshot(self) -> dict:
        avg_dwell = statistics.mean(self.queue_dwell_samples) if self.queue_dwell_samples else 0.0
        longest_wait = max(self.queue_dwell_samples) if self.queue_dwell_samples else 0.0
        p95_wait = self._percentile(self.queue_dwell_samples, 0.95) if len(self.queue_dwell_samples) >= 5 else None
        idle_total_seconds = sum(self.idle_durations)
        longest_idle = max(self.idle_durations) if self.idle_durations else 0.0

        return {
            "live_status": {
                "people_visible": self._live.get("people_visible", 0),
                "zone_counts": self._live.get("zone_counts", {}),
                "active_tracks": self._live.get("active_tracks", 0),
            },
            "business_metrics": {
                "queue_length": self._live.get("queue_length", 0),
                "peak_queue": self.peak_queue,
                "longest_wait_seconds": round(longest_wait, 1),
                "average_dwell_seconds": round(avg_dwell, 1),
                "p95_wait_seconds": round(p95_wait, 1) if p95_wait is not None else None,
                "tables_occupied": self._live.get("tables_occupied", 0),
                "tables_available": self._live.get("tables_available", 0),
                "prep_staff_count": self._live.get("prep_staff_count", 0),
                "potential_idle_staff_now": self._live.get("potential_idle_staff_now", 0),
            },
            "aggregate": {
                "footfall": self.footfall_in,
                "current_occupancy": self._live.get("current_occupancy", 0),
                "peak_people": self.peak_people,
                "peak_queue": self.peak_queue,
                "average_queue_dwell_seconds": round(avg_dwell, 1),
                "longest_wait_seconds": round(longest_wait, 1),
                "potential_abandonments": self.abandonments,
                "potential_idle_staff_events": self.idle_events_count,
                "potential_idle_staff_minutes": round(idle_total_seconds / 60.0, 1),
                "longest_idle_seconds": round(longest_idle, 1),
                "table_clearing_delay_events": self.clearing_delay_events,
                "potential_pickup_delays": self.pickup_delay_events,
                "visible_spill_events": self.spill_events,
            },
        }

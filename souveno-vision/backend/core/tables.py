"""Table state machine (Phase 11).

V0.1 uses a deliberately simple, honest rule set: occupancy is inferred
from whether tracked people currently overlap the table polygon. This is
labelled as a limitation in the UI — it cannot tell a cleared table apart
from one nobody has touched yet without a staff-interaction signal, so
once a table reaches CLEARING_DELAY it stays there until someone sits
down again.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class TableState(str, Enum):
    AVAILABLE = "AVAILABLE"
    OCCUPIED = "OCCUPIED"
    VACATED = "VACATED"
    CLEARING_DELAY = "CLEARING_DELAY"
    UNKNOWN = "UNKNOWN"


@dataclass
class TableStatus:
    table_id: str
    state: TableState
    vacated_seconds_ago: Optional[float] = None
    occupied_seconds: Optional[float] = None


class TableTracker:
    def __init__(self, clearing_delay_seconds: float):
        self.clearing_delay_seconds = clearing_delay_seconds
        self._state: dict[str, TableState] = {}
        self._vacated_at: dict[str, float] = {}
        self._occupied_at: dict[str, float] = {}

    def update(self, table_id: str, occupancy_count: int, timestamp: float) -> TableStatus:
        state = self._state.get(table_id, TableState.AVAILABLE)

        if occupancy_count > 0:
            if state != TableState.OCCUPIED:
                self._occupied_at[table_id] = timestamp
            state = TableState.OCCUPIED
            self._vacated_at.pop(table_id, None)
        else:
            if state == TableState.OCCUPIED:
                state = TableState.VACATED
                self._vacated_at[table_id] = timestamp
            elif state in (TableState.VACATED, TableState.CLEARING_DELAY):
                vacated_at = self._vacated_at.get(table_id, timestamp)
                elapsed = timestamp - vacated_at
                state = TableState.CLEARING_DELAY if elapsed >= self.clearing_delay_seconds else TableState.VACATED
            else:
                state = TableState.AVAILABLE

        self._state[table_id] = state
        vacated_at = self._vacated_at.get(table_id)
        occupied_at = self._occupied_at.get(table_id)
        return TableStatus(
            table_id=table_id,
            state=state,
            vacated_seconds_ago=(timestamp - vacated_at) if vacated_at is not None else None,
            occupied_seconds=(timestamp - occupied_at) if (state == TableState.OCCUPIED and occupied_at is not None) else None,
        )

    def all_states(self) -> dict[str, TableState]:
        return dict(self._state)

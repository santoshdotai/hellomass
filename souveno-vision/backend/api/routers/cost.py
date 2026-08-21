"""Phase 22 — Cost Impact Estimator. Every figure returned here is
illustrative, derived from detected-event counts, never a proven saving."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db import crud
from backend.db.database import get_db
from backend.schemas.api_schemas import CostEstimateRequest

router = APIRouter(prefix="/api/cost", tags=["cost"])


@router.post("/estimate")
def estimate(payload: CostEstimateRequest, db: Session = Depends(get_db)):
    session = crud.get_session(db, payload.session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    summary = crud.get_summary(db, payload.session_id)
    if not summary:
        raise HTTPException(400, "Run analysis to completion first to generate a summary")

    import json
    stats = json.loads(summary.stats_json)

    video_hours = max(stats.get("video_duration_seconds", 0) / 3600.0, 1e-6)
    idle_minutes_observed = 0.0
    for e in crud.list_events(db, payload.session_id):
        pass  # events already summarized into stats

    # Extrapolate the idle time observed in this clip to a full operating day, illustratively only.
    idle_minutes_per_hour = (stats.get("event_type_counts", {}).get("POTENTIAL_IDLE_STAFF", 0) and
                              _idle_minutes_from_label(stats)) / video_hours if video_hours else 0
    idle_hours_per_day_equiv = round((idle_minutes_per_hour * payload.operating_hours_per_day) / 60.0, 2)
    monthly_labour_exposure = round(idle_hours_per_day_equiv * payload.staff_hourly_cost *
                                     payload.working_days_per_month, 2)

    abandonments = stats.get("potential_queue_abandonments", 0)
    abandonments_per_hour = abandonments / video_hours if video_hours else 0
    monthly_abandonment_orders = round(abandonments_per_hour * payload.operating_hours_per_day *
                                        payload.working_days_per_month, 1)
    monthly_abandonment_revenue_exposure = round(monthly_abandonment_orders * payload.average_order_value, 2)

    return {
        "illustrative_estimate": True,
        "disclaimer": "All figures below are illustrative estimates extrapolated from this single recorded "
                       "session. They are not proven savings and are not connected to POS/payroll data.",
        "inputs": payload.model_dump(),
        "labour": {
            "potential_labour_inefficiency_hours_per_day_equivalent": idle_hours_per_day_equiv,
            "illustrative_monthly_labour_exposure": monthly_labour_exposure,
        },
        "queue_abandonment": {
            "estimated_monthly_abandonment_events": monthly_abandonment_orders,
            "illustrative_monthly_revenue_exposure": monthly_abandonment_revenue_exposure,
        },
        "wastage": {
            "illustrative_monthly_spillage_estimate": payload.estimated_monthly_spillage,
            "note": "User-entered baseline — not derived from spill detections (spill detection is experimental).",
        },
    }


def _idle_minutes_from_label(stats: dict) -> float:
    label = stats.get("total_potential_idle_time_label", "0:00:00")
    parts = [int(p) for p in label.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts
    return h * 60 + m + s / 60.0

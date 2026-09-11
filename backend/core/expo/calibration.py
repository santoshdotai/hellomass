"""Learn from actuals: after each show Santosh enters what really happened, and the
agent scales its future estimates by the observed ratio (actual ÷ estimate), separately
for exhibits and visits. One data point moves the factor a little (shrunk towards 1.0);
five or more move it fully. Footfall actuals also overwrite the event's expected figure.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.core.expo import scoring
from backend.core.expo.catalog import get_event
from backend.db import models

METRICS = ("leads", "paid_pilots", "cost", "footfall", "revenue")
FULL_WEIGHT_AT = 5  # actuals needed before the factor is trusted fully


def _est(ev: dict[str, Any]) -> dict[str, float]:
    e = scoring.evaluate(ev)
    f, b = e["funnel"], e["budget"]
    mid = lambda r: (r[0] + r[1]) / 2 if isinstance(r, list) else float(r)
    return {"leads": mid(f["leads"]), "paid_pilots": mid(f["paid_pilots"]), "cost": mid(b["total_inr"]),
            "footfall": float((ev.get("expected") or {}).get("visitors") or 0), "revenue": mid(f["paid_pilots"]) * 1.0}


def actuals_dict(row: models.ExpoActuals) -> dict[str, Any]:
    ev = get_event(row.event_id) or {}
    est = _est(ev) if ev else {}
    e = scoring.evaluate(ev) if ev else {}
    out = {"event_id": row.event_id, "event_name": ev.get("name", row.event_id), "mode": row.mode or ev.get("mode", ""),
           "actual_cost_inr": row.actual_cost_inr, "footfall_visitors": row.footfall_visitors, "leads": row.leads, "qualified": row.qualified,
           "demos": row.demos, "paid_pilots": row.paid_pilots, "revenue_inr": row.revenue_inr, "subsidy_received_inr": row.subsidy_received_inr,
           "stall_number": row.stall_number, "best_segments": [x for x in (row.best_segments or "").split(",") if x], "notes": row.notes,
           "recorded_at": row.recorded_at.isoformat() if row.recorded_at else None}
    if ev:
        out["estimate"] = {"leads": e["funnel"]["leads"], "paid_pilots": e["funnel"]["paid_pilots"], "cost_inr": e["budget"]["total_inr"],
                           "footfall_visitors": (ev.get("expected") or {}).get("visitors")}
        out["variance"] = {"leads_ratio": round(row.leads / est["leads"], 2) if est["leads"] else None,
                           "pilots_ratio": round(row.paid_pilots / est["paid_pilots"], 2) if est["paid_pilots"] else None,
                           "cost_ratio": round(row.actual_cost_inr / est["cost"], 2) if est["cost"] and row.actual_cost_inr else None,
                           "footfall_ratio": round(row.footfall_visitors / est["footfall"], 2) if est["footfall"] and row.footfall_visitors else None}
        out["pl_actual_inr"] = row.revenue_inr + row.subsidy_received_inr - row.actual_cost_inr
    return out


def factors(db: Session) -> dict[str, Any]:
    """Per-mode multipliers to apply to future estimates, shrunk towards 1.0 while data is thin."""
    rows = db.query(models.ExpoActuals).all()
    acc: dict[str, dict[str, list[float]]] = {"exhibit": {m: [] for m in METRICS}, "visit": {m: [] for m in METRICS}}
    for r in rows:
        ev = get_event(r.event_id)
        if not ev:
            continue
        mode = r.mode or ev.get("mode", "visit")
        est = _est(ev)
        if r.leads and est["leads"]:
            acc[mode]["leads"].append(r.leads / est["leads"])
        if r.paid_pilots and est["paid_pilots"]:
            acc[mode]["paid_pilots"].append(r.paid_pilots / est["paid_pilots"])
        if r.actual_cost_inr and est["cost"]:
            acc[mode]["cost"].append(r.actual_cost_inr / est["cost"])
        if r.footfall_visitors and est["footfall"]:
            acc[mode]["footfall"].append(r.footfall_visitors / est["footfall"])
    out: dict[str, Any] = {"n_actuals": len(rows), "by_mode": {}}
    for mode, mets in acc.items():
        out["by_mode"][mode] = {}
        for m, vals in mets.items():
            if vals:
                raw = sum(vals) / len(vals)
                w = min(1.0, len(vals) / FULL_WEIGHT_AT)
                out["by_mode"][mode][m] = {"factor": round(1.0 + (raw - 1.0) * w, 3), "raw": round(raw, 3), "n": len(vals)}
            else:
                out["by_mode"][mode][m] = {"factor": 1.0, "raw": None, "n": 0}
    out["note"] = ("No actuals yet: estimates are uncalibrated." if not rows else
                   f"Calibrated from {len(rows)} show(s); a factor of 0.8 means real results ran 20% below the estimate. Full weight after {FULL_WEIGHT_AT} shows per mode.")
    return out


def factor(fx: dict[str, Any], mode: str, metric: str) -> float:
    return float(((fx.get("by_mode") or {}).get(mode) or {}).get(metric, {}).get("factor", 1.0))


def calibrate_row(row: dict[str, Any], fx: dict[str, Any]) -> dict[str, Any]:
    """Add calibrated_* fields to a finance row."""
    mode = row["mode"]
    fl, fp, fc = factor(fx, mode, "leads"), factor(fx, mode, "paid_pilots"), factor(fx, mode, "cost")
    value = row["value_per_client_inr"]
    leads = [round(row["leads"][0] * fl), round(row["leads"][1] * fl)]
    pilots = [round(row["conversions"][0] * fp, 1), round(row["conversions"][1] * fp, 1)]
    cost = [round(row["net_cost_inr"][0] * fc), round(row["net_cost_inr"][1] * fc)]
    rev = [round(pilots[0] * value), round(pilots[1] * value)]
    row["calibrated"] = {"leads": leads, "conversions": pilots, "net_cost_inr": cost, "revenue_inr": rev, "pl_inr": [rev[0] - cost[1], rev[1] - cost[0]],
                         "factors": {"leads": fl, "paid_pilots": fp, "cost": fc}}
    return row

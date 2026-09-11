"""Finance tab: profit-or-loss view of the expo programme for a chosen horizon.

Pick a horizon (1 week … 12 months from today) and get every show starting inside it,
exhibits and visits separated, with: total cost, assumed leads, what those leads are
worth as pipeline, expected conversions (paid pilots that become clients), conversion
worth in INR and USD, conversion %, subsidy money back, P&L and ROI, plus who the best
bets on that floor are. All money comes from the same funnel and budget the event cards
show, and the per-client value from ``_meta.deal_economics`` in data/expo/events.json.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from backend.core.expo import scoring, subsidy
from backend.core.expo.catalog import list_events, meta

HORIZONS: list[tuple[str, str, int]] = [
    ("1w", "in 1 week", 7), ("2w", "in 2 weeks", 14), ("3w", "in 3 weeks", 21),
    ("1m", "in 1 month", 30), ("2m", "in 2 months", 61), ("3m", "in 3 months", 91), ("4m", "in 4 months", 122),
    ("5m", "in 5 months", 152), ("6m", "in 6 months", 183), ("7m", "in 7 months", 213), ("8m", "in 8 months", 244),
    ("9m", "in 9 months", 274), ("10m", "in 10 months", 304), ("11m", "in 11 months", 335), ("12m", "in 12 months", 365),
]
SEGMENT_NAMES = scoring.SEGMENT_NAMES if hasattr(scoring, "SEGMENT_NAMES") else {}


def horizon_days(key: str) -> int:
    for k, _, days in HORIZONS:
        if k == key:
            return days
    raise KeyError(key)


def _econ() -> dict[str, Any]:
    return meta().get("deal_economics") or {"fx_inr_per_usd": 84.0, "quote_desk": {"first_year_value_inr": 169000}, "vision_ai": {"first_year_value_inr": 350000}, "both": {"first_year_value_inr": 259500}, "lead_to_client_probability": 0.0525}


def _best_bets(ev: dict[str, Any], ev_eval: dict[str, Any]) -> dict[str, Any]:
    segs = meta().get("icp_segments", {})
    lp = ev_eval["lead_product"]
    keys = (ev.get("icp_vision") or []) if lp == "vision_ai" else (ev.get("icp") or []) if lp == "quote_desk" else list(dict.fromkeys((ev.get("icp") or []) + (ev.get("icp_vision") or [])))
    return {
        "lead_product": lp,
        "segments": [{"key": k, "name": segs.get(k, k)} for k in keys[:5]],
        "who": ev.get("why", ""),
        "where": (ev.get("stall") or {}).get("hall_hint", ""),
    }


def row(ev: dict[str, Any], today: date) -> dict[str, Any]:
    e = scoring.evaluate(ev)
    econ = _econ()
    fx = float(econ.get("fx_inr_per_usd", 84.0))
    value = int((econ.get(e["lead_product"]) or econ.get("both") or {}).get("first_year_value_inr", 200000))
    p_close = float(econ.get("lead_to_client_probability", 0.0525))
    f, b = e["funnel"], e["budget"]
    leads = f["leads"]; pilots = f["paid_pilots"]
    cost = b["total_inr"] if isinstance(b["total_inr"], list) else [b["total_inr"], b["total_inr"]]
    pipeline = [round(leads[0] * p_close * value), round(leads[1] * p_close * value)]
    revenue = [round(pilots[0] * value), round(pilots[1] * value)]
    sub = subsidy.for_event(ev, today)
    refund = sub["estimated_refund_inr"]
    net_cost = [max(0, cost[0] - refund[1]), max(0, cost[1] - refund[0])]
    pl = [revenue[0] - net_cost[1], revenue[1] - net_cost[0]]
    roi = [round(pl[0] / net_cost[1] * 100) if net_cost[1] else None, round(pl[1] / net_cost[0] * 100) if net_cost[0] else None]
    conv_pct = round(pilots[1] / leads[1] * 100, 1) if leads[1] else 0.0
    start = date.fromisoformat(ev["start"])
    return {
        "id": ev["id"], "name": ev["name"], "start": ev["start"], "end": ev["end"], "city": ev["city"], "mode": ev["mode"],
        "days_away": (start - today).days, "stars": e["stars"], "total_score": e["total_score"], "lead_product": e["lead_product"],
        "cost_inr": cost, "subsidy_refund_inr": refund, "net_cost_inr": net_cost,
        "leads": leads, "pipeline_inr": pipeline, "pipeline_usd": [round(pipeline[0] / fx), round(pipeline[1] / fx)],
        "conversions": pilots, "conversion_pct": conv_pct, "client_probability_pct": f["client_probability_pct"],
        "revenue_inr": revenue, "revenue_usd": [round(revenue[0] / fx), round(revenue[1] / fx)],
        "pl_inr": pl, "pl_usd": [round(pl[0] / fx), round(pl[1] / fx)], "roi_pct": roi,
        "value_per_client_inr": value, "best_bets": _best_bets(ev, e), "budget_label": b.get("label", ""),
        "verdict": "profit" if pl[0] > 0 else "profit at the high case" if pl[1] > 0 else "loss",
    }


def _sum(rows: list[dict[str, Any]], key: str) -> list[int]:
    return [sum(r[key][0] for r in rows), sum(r[key][1] for r in rows)]


def _totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    fx = float(_econ().get("fx_inr_per_usd", 84.0))
    if not rows:
        return {"shows": 0, "cost_inr": [0, 0], "net_cost_inr": [0, 0], "subsidy_refund_inr": [0, 0], "leads": [0, 0], "pipeline_inr": [0, 0], "conversions": [0, 0], "revenue_inr": [0, 0], "revenue_usd": [0, 0], "pl_inr": [0, 0], "pl_usd": [0, 0], "roi_pct": [None, None], "conversion_pct": 0}
    t = {k: _sum(rows, k) for k in ("cost_inr", "net_cost_inr", "subsidy_refund_inr", "leads", "pipeline_inr", "revenue_inr", "pl_inr")}
    conv = [round(sum(r["conversions"][0] for r in rows), 1), round(sum(r["conversions"][1] for r in rows), 1)]
    t.update({"shows": len(rows), "conversions": conv,
              "conversion_pct": round(conv[1] / t["leads"][1] * 100, 1) if t["leads"][1] else 0,
              "revenue_usd": [round(t["revenue_inr"][0] / fx), round(t["revenue_inr"][1] / fx)],
              "pl_usd": [round(t["pl_inr"][0] / fx), round(t["pl_inr"][1] / fx)],
              "roi_pct": [round(t["pl_inr"][0] / t["net_cost_inr"][1] * 100) if t["net_cost_inr"][1] else None,
                          round(t["pl_inr"][1] / t["net_cost_inr"][0] * 100) if t["net_cost_inr"][0] else None]})
    return t


def report(horizon: str = "1m", today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    days = horizon_days(horizon)
    end = today + timedelta(days=days)
    rows = [row(ev, today) for ev in list_events() if today <= date.fromisoformat(ev["start"]) <= end]
    rows.sort(key=lambda r: r["start"])
    ex = [r for r in rows if r["mode"] == "exhibit"]
    vi = [r for r in rows if r["mode"] == "visit"]
    best = sorted(rows, key=lambda r: r["pl_inr"][1], reverse=True)[:5]
    return {
        "horizon": horizon, "horizon_label": next(l for k, l, _ in HORIZONS if k == horizon), "today": today.isoformat(), "window_end": end.isoformat(),
        "horizons": [{"key": k, "label": l, "days": dd} for k, l, dd in HORIZONS],
        "exhibits": ex, "visits": vi,
        "totals": {"exhibits": _totals(ex), "visits": _totals(vi), "all": _totals(rows)},
        "best_bets": [{"id": r["id"], "name": r["name"], "mode": r["mode"], "pl_inr": r["pl_inr"], "roi_pct": r["roi_pct"], "lead_product": r["lead_product"]} for r in best],
        "assumptions": _econ(),
        "disclaimer": "Costs are public fare/rate ranges (not quotes); leads and conversions come from the funnel assumptions in the scoring doc; revenue = paid pilots × first-year value per client. Low case first, high case second.",
    }


def all_horizons(today: date | None = None) -> dict[str, Any]:
    """Every horizon precomputed (used by the phone dashboard build)."""
    return {k: report(k, today) for k, _, _ in HORIZONS}

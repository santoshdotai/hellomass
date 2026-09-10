"""Event scoring — turns the researched component scores into a 1-5 star
rating, a client-probability estimate and a budget, using Souveno's own
funnel assumptions (Barakah Systems validation report, Aug 2026).

Everything here is deterministic and unit-tested; no LLM is involved, so the
numbers are explainable line by line on the dashboard.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Any

from backend.core.expo.catalog import meta

COMPONENT_MAX = {
    "icp_fit": 40,
    "footfall": 15,
    "decision_makers": 15,
    "geography_cost": 10,
    "competition_noise": 10,
    "timing_fit": 10,
}


def total_score(score: dict[str, int]) -> int:
    return int(sum(min(score.get(k, 0), mx) for k, mx in COMPONENT_MAX.items()))


def stars_from_total(total: int) -> float:
    """0-100 -> 1.0..5.0 in half-star steps (floor(x*2+0.5)/2, then clamped)."""
    raw = total / 20.0
    half = math.floor(raw * 2 + 0.5) / 2
    return float(max(1.0, min(5.0, half)))


def stars(score: dict[str, int]) -> float:
    return stars_from_total(total_score(score))


def event_days(ev: dict[str, Any]) -> int:
    return (date.fromisoformat(ev["end"]) - date.fromisoformat(ev["start"])).days + 1


def funnel(ev: dict[str, Any], mode: str | None = None, assumptions: dict[str, float] | None = None) -> dict[str, Any]:
    """Expected leads -> qualified -> demos -> paid pilots for exhibiting or
    visiting. Visiting counts the *exhibitors* as prospects (for Souveno the
    manufacturers on the floor are the buyers)."""
    a = assumptions or meta()["funnel_assumptions"]
    mode = mode or ev.get("mode", "visit")
    icp_factor = min(ev["score"].get("icp_fit", 0), 40) / 40.0
    days = event_days(ev)
    visitors = ev["expected"]["visitors"]
    exhibitors = ev["expected"]["exhibitors"]

    if mode == "exhibit":
        # Cap reach: a single 9-18 sqm stall cannot convert the whole floor.
        reachable = min(visitors, 60000)
        leads_high = reachable * icp_factor * a["exhibit_capture_rate"]
        leads_low = leads_high * 0.5
        # Plus walking the floor for 2 hours a day.
        floor = min(exhibitors, 20 * days) * icp_factor * a["visit_share_rate"]
        leads_low += floor * 0.5
        leads_high += floor
    else:
        booths = min(exhibitors, a["visit_booths_per_day"] * min(days, 3))
        leads_high = booths * icp_factor * a["visit_share_rate"]
        leads_low = leads_high * 0.5

    def chain(leads: float) -> dict[str, float]:
        q = leads * a["qualified_rate"]
        d = q * a["demo_rate"]
        p = d * a["paid_pilot_rate"]
        return {"leads": leads, "qualified": q, "demos": d, "paid_pilots": p}

    low, high = chain(leads_low), chain(leads_high)
    p_at_least_one = 1 - math.exp(-low["paid_pilots"])
    return {
        "mode": mode,
        "days": days,
        "leads": [round(low["leads"]), round(high["leads"])],
        "qualified": [round(low["qualified"]), round(high["qualified"])],
        "demos": [round(low["demos"]), round(high["demos"])],
        "paid_pilots": [round(low["paid_pilots"], 1), round(high["paid_pilots"], 1)],
        "p_at_least_one_client": round(p_at_least_one, 2),
        "client_probability_pct": int(round(p_at_least_one * 100)),
    }


def budget(ev: dict[str, Any], mode: str | None = None, travellers: int = 2, hotel_tier: str = "mid") -> dict[str, Any]:
    """Illustrative INR budget: stall + flights + hotel + per-diem."""
    mode = mode or ev.get("mode", "visit")
    days = event_days(ev)
    stall = ev.get("stall", {})
    sqm = stall.get("suggested_sqm", 0) if mode == "exhibit" else 0
    stall_cost = sqm * stall.get("shell_rate_inr_sqm", 0)
    fabrication = 4500 * sqm if sqm else 0  # basic branded fascia + counter + screen

    travel = ev.get("travel", {})
    lo, hi = travel.get("flight_oneway_inr", [0, 0])
    flights = [lo * 2 * travellers, hi * 2 * travellers]

    hotels = travel.get("hotels", [])
    nights = days + 1 if travel.get("airport") else 0
    pick = next((h for h in hotels if h["tier"] == hotel_tier), hotels[0] if hotels else None)
    hotel = [0, 0]
    if pick and nights:
        hotel = [pick["inr_night"][0] * nights, pick["inr_night"][1] * nights]
    per_diem = 1500 * travellers * (days + (1 if nights else 0))
    if ev.get("city") == "Dubai":
        per_diem *= 3

    total_lo = stall_cost + fabrication + flights[0] + hotel[0] + per_diem
    total_hi = stall_cost + fabrication + flights[1] + hotel[1] + per_diem
    return {
        "mode": mode,
        "stall_sqm": sqm,
        "stall_inr": stall_cost,
        "fabrication_inr": fabrication,
        "flights_inr": flights,
        "hotel_nights": nights,
        "hotel_pick": pick["name"] if pick else None,
        "hotel_inr": hotel,
        "per_diem_inr": per_diem,
        "total_inr": [int(total_lo), int(total_hi)],
        "label": "ILLUSTRATIVE ESTIMATE — public fare/rate ranges as of Sept 2026, not quotes",
    }


def evaluate(ev: dict[str, Any], travellers: int = 2) -> dict[str, Any]:
    total = total_score(ev["score"])
    st = stars(ev["score"])
    fn = funnel(ev)
    bd = budget(ev, travellers=travellers)
    mid_clients = (fn["paid_pilots"][0] + fn["paid_pilots"][1]) / 2
    mid_cost = (bd["total_inr"][0] + bd["total_inr"][1]) / 2
    return {
        "id": ev["id"],
        "name": ev["name"],
        "total_score": total,
        "stars": st,
        "stars_label": f"{st:.1f} / 5",
        "components": {k: {"score": ev["score"].get(k, 0), "max": mx} for k, mx in COMPONENT_MAX.items()},
        "funnel": fn,
        "funnel_alt": funnel(ev, mode="visit" if fn["mode"] == "exhibit" else "exhibit"),
        "budget": bd,
        "cost_per_expected_client_inr": int(mid_cost / mid_clients) if mid_clients > 0 else None,
    }


def rank(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scored = [{**ev, "evaluation": evaluate(ev)} for ev in events]
    return sorted(scored, key=lambda e: (-e["evaluation"]["total_score"], e["start"]))

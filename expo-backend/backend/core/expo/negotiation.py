"""Stall negotiation rules.

Turns an organiser's quote into a target price, a walk-away price, the asks
that cost the organiser little, and a reply the agent can send from
souveno30@gmail.com. Deterministic, so the nightly routine negotiates the
same way every time and never drifts past what Santosh approved:

  * target  = the lower of the catalogue estimate and 82% of the quoted rate
  * walk-away = catalogue estimate x 1.10 (above this the agent stops and
    asks Santosh instead of agreeing)
  * the agent never confirms a booking or a payment; it says the advance
    follows once the proforma matches the agreed terms and Santosh approves
"""
from __future__ import annotations

from typing import Any

from backend.core.expo.catalog import get_event
from backend.core.expo.planner import SOUVENO_PROFILE

DISCOUNT_ASK = 0.18       # open at 18% below the quoted rate
FIRST_COUNTER = 0.12      # accept anything 12%+ below quote without a second round
WALK_AWAY_OVER_ESTIMATE = 1.10
FREE_ASKS = [
    "fascia name board with the Souveno logo",
    "1 table, 2 chairs, carpet and 2 spotlights included",
    "a 5 A power point included (we run a live demo)",
    "2 extra exhibitor badges",
    "company listing in the show directory / app and one social post",
    "1 complimentary conference / seminar pass",
    "payment in two instalments: 50% advance, 50% thirty days before the show",
]
STALL_PREFERENCES = [
    "corner stall at the row rate (not the corner premium)",
    "main aisle, within 30 m of the entrance or the food court",
    "same row as the anchor exhibitors of our segment (buyers walk that row)",
    "not behind a pillar, not at a dead-end aisle, not next to the loading door",
    "favourable numbers where the choice is free: 1, 3, 5, 7, 9, 11, 21, 27, 45, 63",
]


def _estimate(ev: dict[str, Any]) -> tuple[int, int, int]:
    st = ev.get("stall") or {}
    sqm = int(st.get("suggested_sqm") or 9)
    rate = int(st.get("shell_rate_inr_sqm") or 10000)
    return sqm, rate, sqm * rate


def evaluate_quote(event_id: str, quoted_rate_inr_sqm: float, sqm: float | None = None,
                   includes: list[str] | None = None, msme_rate_inr_sqm: float | None = None,
                   early_bird_rate_inr_sqm: float | None = None, offered_stalls: list[str] | None = None) -> dict[str, Any]:
    ev = get_event(event_id)
    if not ev:
        raise KeyError(event_id)
    est_sqm, est_rate, est_total = _estimate(ev)
    sqm = float(sqm or est_sqm)
    best_listed = min(x for x in (quoted_rate_inr_sqm, msme_rate_inr_sqm, early_bird_rate_inr_sqm) if x)
    target_rate = min(est_rate, round(best_listed * (1 - DISCOUNT_ASK)))
    accept_rate = round(best_listed * (1 - FIRST_COUNTER))
    walk_away_rate = round(est_rate * WALK_AWAY_OVER_ESTIMATE)
    includes = [x.lower() for x in (includes or [])]
    missing = [a for a in FREE_ASKS if not any(k in " ".join(includes) for k in a.split()[:2])]
    verdict = ("accept" if best_listed <= accept_rate or best_listed <= est_rate
               else "counter" if best_listed <= walk_away_rate * 1.35
               else "escalate")
    if verdict == "accept" and best_listed <= est_rate:
        note = "Quote is at or under our estimate: accept the rate, still ask for the free extras and the instalment plan."
    elif verdict == "accept":
        note = "Quote is within 12% of our estimate: accept after one ask for extras."
    elif verdict == "counter":
        note = f"Counter at ₹{target_rate:,}/sqm; settle anywhere up to ₹{walk_away_rate:,}/sqm. Above that, stop and ask Santosh."
    else:
        note = f"Quote is far above the ₹{walk_away_rate:,}/sqm walk-away line: do not negotiate further, send it to Santosh with the numbers."
    return {
        "event_id": event_id, "event_name": ev["name"], "sqm": sqm,
        "estimate_rate_inr_sqm": est_rate, "estimate_total_inr": est_total,
        "quoted_rate_inr_sqm": quoted_rate_inr_sqm, "best_listed_rate_inr_sqm": best_listed,
        "target_rate_inr_sqm": target_rate, "accept_rate_inr_sqm": accept_rate, "walk_away_rate_inr_sqm": walk_away_rate,
        "target_total_inr": round(target_rate * sqm), "walk_away_total_inr": round(walk_away_rate * sqm),
        "verdict": verdict, "note": note, "asks": missing, "stall_preferences": STALL_PREFERENCES,
        "offered_stalls": offered_stalls or [],
        "reply": counter_reply(ev, sqm, best_listed, target_rate, missing, offered_stalls or [], verdict),
    }


def counter_reply(ev: dict[str, Any], sqm: float, quoted: float, target: float, asks: list[str],
                  offered_stalls: list[str], verdict: str) -> str:
    p = SOUVENO_PROFILE
    stall_line = (f"Of the stalls you offered ({', '.join(offered_stalls)}), we would take the corner / main-aisle one nearest the entrance."
                  if offered_stalls else "We would like a corner or main-aisle stall within 30 m of the entrance; please send the floor plan with the free stalls marked.")
    if verdict == "accept":
        money = (f"The rate of ₹{quoted:,.0f}/sqm for {sqm:g} sqm shell scheme works for us.")
    elif verdict == "counter":
        money = (f"As a first-time exhibitor and a Udyam-registered micro enterprise, we can commit today at ₹{target:,.0f}/sqm for {sqm:g} sqm shell scheme "
                 f"(₹{target * sqm:,.0f} + GST). If there is an MSME, early-bird or startup rate that gets us there, please apply it.")
    else:
        money = (f"₹{quoted:,.0f}/sqm is above what we have budgeted for this show. If an MSME pavilion, startup pod or shared stall option exists at a lower rate, please send it.")
    ask_lines = "\n".join(f"- {a}" for a in asks[:5])
    return (f"Dear {ev.get('organiser', 'team')},\n\nThank you for the rate card for {ev['name']}.\n\n{money}\n\n{stall_line}\n\n"
            f"Could you include:\n{ask_lines}\n\n"
            "Once the proforma invoice reflects this, our advance follows from the Souveno current account after our founder's sign-off.\n\n"
            f"Regards,\n{p['contact_name']}\n{p['designation']}, {p['legal_name']}\nGSTIN {p['gstin']} · {p['phone']} · {p['email']}")

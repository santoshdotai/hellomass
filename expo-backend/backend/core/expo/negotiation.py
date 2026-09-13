"""Stall negotiation rules.

Turns an organiser's quote into a target price, a walk-away price, the asks
that cost the organiser little, and a reply the agent can send from
souveno30@gmail.com. Deterministic, so the nightly routine negotiates the
same way every time and never drifts past what Santosh approved:

  * Santosh's rules (13 Sep 2026), editable in Settings → Negotiation:
      - quote below ₹10,000/sqm  -> we open at ₹5,000/sqm (and always at
        least ₹1,000 below the quote: a ₹6,000 quote gets a ₹5,000 ask)
      - quote ₹10,000 to ₹13,000  -> we open at ₹6,000/sqm ("our minimum")
      - quote above ₹13,000       -> we open at ₹6,000/sqm and flag it for
        Santosh if the organiser will not come down
      - settle ceilings (what we will pay at most, per band): ₹6,000 below
        10k, ₹8,000 from 10k up; above the ceiling the desk stops and asks
        Santosh instead of agreeing
  * a first quote is never accepted: the desk always counters once
  * the agent never confirms a booking or a payment; it says the advance
    follows once the proforma matches the agreed terms and Santosh approves
"""
from __future__ import annotations

from typing import Any

from backend.core.expo.catalog import get_event
from backend.core.expo.planner import SOUVENO_PROFILE

DEFAULT_RULES = {
    "open_below_10k": 5000,     # our opening ask when the quote is under ₹10,000/sqm
    "open_10k_to_13k": 6000,    # our opening ask for quotes of ₹10,000 to ₹13,000/sqm ("our minimum")
    "open_above_13k": 6000,     # opening ask above ₹13,000/sqm (escalated to Santosh if refused)
    "step_below_quote": 1000,   # always ask at least this much below the quote
    "settle_max_below_10k": 6000,   # the most we pay per sqm when the quote was under 10k
    "settle_max_10k_plus": 8000,    # the most we pay per sqm when the quote was 10k or more
    "band_low": 10000, "band_high": 13000,
    "max_rounds": 2,            # counters before we settle at the best offer inside the ceiling
    "round_to": 500,            # counters are rounded to this
}


def rules(overrides: dict[str, Any] | None = None) -> dict[str, int]:
    """Bargaining rules: defaults merged with whatever Santosh saved in Settings."""
    r = dict(DEFAULT_RULES)
    for k, v in (overrides or {}).items():
        if k in r and v not in (None, ""):
            try:
                r[k] = int(v)
            except (TypeError, ValueError):
                pass
    return r


def band(quote: float, r: dict[str, int]) -> str:
    return "below_10k" if quote < r["band_low"] else "10k_to_13k" if quote <= r["band_high"] else "above_13k"


def opening_base(quote: float, r: dict[str, int]) -> int:
    b = band(quote, r)
    return r["open_below_10k"] if b == "below_10k" else r["open_10k_to_13k"] if b == "10k_to_13k" else r["open_above_13k"]


def opening_counter(quote: float, r: dict[str, int]) -> int:
    """Our first ask per sqm for a quoted rate (Santosh's bands, and never less than step_below_quote under the quote)."""
    return int(min(opening_base(quote, r), quote - r["step_below_quote"]))


def settle_max(quote: float, r: dict[str, int]) -> int:
    return r["settle_max_below_10k"] if band(quote, r) == "below_10k" else r["settle_max_10k_plus"]


def next_move(quote: float, offer_now: float, round_no: int = 1, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """What the desk does when the organiser's current offer is `offer_now` (the first quote or a revised one).

    round_no = how many counters we have already sent (0 before the first)."""
    r = rules(overrides)
    opening, ceiling = opening_counter(quote, r), settle_max(quote, r)
    step = r["round_to"]
    if offer_now <= opening or (round_no == 0 and offer_now <= opening_base(quote, r)):
        return {"verdict": "accept", "rate": int(offer_now), "opening": opening, "ceiling": ceiling, "band": band(quote, r),
                "note": f"₹{offer_now:,.0f}/sqm is at or under our opening ask of ₹{opening_base(quote, r):,}/sqm: accept, still ask for the free extras and two instalments."}
    if round_no == 0:
        return {"verdict": "counter", "rate": opening, "opening": opening, "ceiling": ceiling, "band": band(quote, r),
                "note": f"First quote ₹{offer_now:,.0f}/sqm (band {band(quote, r).replace('_', ' ')}): open at ₹{opening:,}/sqm; settle up to ₹{ceiling:,}/sqm."}
    if offer_now <= ceiling:
        if round_no >= r["max_rounds"]:
            return {"verdict": "accept", "rate": int(offer_now), "opening": opening, "ceiling": ceiling, "band": band(quote, r),
                    "note": f"Organiser came to ₹{offer_now:,.0f}/sqm inside our ceiling of ₹{ceiling:,} after {round_no} rounds: accept."}
        mid = int(round(((opening + offer_now) / 2) / step) * step)
        mid = max(opening, min(mid, ceiling))
        return {"verdict": "counter", "rate": mid, "opening": opening, "ceiling": ceiling, "band": band(quote, r),
                "note": f"Organiser is at ₹{offer_now:,.0f}/sqm, inside the ceiling: one more counter at ₹{mid:,}/sqm, then settle."}
    if round_no < r["max_rounds"]:
        return {"verdict": "counter", "rate": ceiling, "opening": opening, "ceiling": ceiling, "band": band(quote, r),
                "note": f"Organiser is still at ₹{offer_now:,.0f}/sqm, above our ceiling of ₹{ceiling:,}: counter at the ceiling (round {round_no + 1})."}
    return {"verdict": "escalate", "rate": ceiling, "opening": opening, "ceiling": ceiling, "band": band(quote, r),
            "note": f"Organiser will not come under ₹{ceiling:,}/sqm after {round_no} rounds: stop and ask Santosh (best offer ₹{offer_now:,.0f}/sqm)."}


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
                   early_bird_rate_inr_sqm: float | None = None, offered_stalls: list[str] | None = None,
                   round_no: int = 0, rule_overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    ev = get_event(event_id)
    if not ev:
        raise KeyError(event_id)
    est_sqm, est_rate, est_total = _estimate(ev)
    sqm = float(sqm or est_sqm)
    best_listed = min(x for x in (quoted_rate_inr_sqm, msme_rate_inr_sqm, early_bird_rate_inr_sqm) if x)
    move = next_move(best_listed, best_listed, round_no, rule_overrides)
    target_rate, walk_away_rate = move["opening"], move["ceiling"]
    includes = [x.lower() for x in (includes or [])]
    missing = [a for a in FREE_ASKS if not any(k in " ".join(includes) for k in a.split()[:2])]
    verdict = move["verdict"]
    return {
        "event_id": event_id, "event_name": ev["name"], "sqm": sqm,
        "estimate_rate_inr_sqm": est_rate, "estimate_total_inr": est_total,
        "quoted_rate_inr_sqm": quoted_rate_inr_sqm, "best_listed_rate_inr_sqm": best_listed, "band": move["band"],
        "target_rate_inr_sqm": target_rate, "counter_rate_inr_sqm": move["rate"], "accept_rate_inr_sqm": target_rate, "walk_away_rate_inr_sqm": walk_away_rate,
        "target_total_inr": round(target_rate * sqm), "walk_away_total_inr": round(walk_away_rate * sqm),
        "advance_at_counter_inr": round(move["rate"] * sqm * 1.18 * 0.5), "advance_at_quote_inr": round(best_listed * sqm * 1.18 * 0.5),
        "verdict": verdict, "note": move["note"], "asks": missing, "stall_preferences": STALL_PREFERENCES,
        "offered_stalls": offered_stalls or [], "rules": rules(rule_overrides),
        "reply": counter_reply(ev, sqm, best_listed, move["rate"], missing, offered_stalls or [], verdict),
    }


def counter_reply(ev: dict[str, Any], sqm: float, quoted: float, target: float, asks: list[str],
                  offered_stalls: list[str], verdict: str) -> str:
    p = SOUVENO_PROFILE
    stall_line = (f"Of the stalls you offered ({', '.join(offered_stalls)}), we would take the corner / main-aisle one nearest the entrance."
                  if offered_stalls else "We would like a corner or main-aisle stall within 30 m of the entrance; please send the floor plan with the free stalls marked.")
    if verdict == "accept":
        money = (f"The rate of ₹{quoted:,.0f}/sqm for {sqm:g} sqm shell scheme works for us.")
    elif verdict == "counter":
        money = (f"As a first-time exhibitor and a Udyam-registered micro enterprise, our budget for this show is ₹{target:,.0f}/sqm for {sqm:g} sqm shell scheme "
                 f"(₹{target * sqm:,.0f} + GST), and we can confirm today at that rate. If there is an MSME, early-bird or startup rate that gets us there, please apply it.")
    else:
        money = (f"₹{quoted:,.0f}/sqm is above what we have budgeted for this show. If an MSME pavilion, startup pod or shared stall option exists at a lower rate, please send it.")
    ask_lines = "\n".join(f"- {a}" for a in asks[:5])
    return (f"Dear {ev.get('organiser', 'team')},\n\nThank you for the rate card for {ev['name']}.\n\n{money}\n\n{stall_line}\n\n"
            f"Could you include:\n{ask_lines}\n\n"
            "Once the proforma invoice reflects this, our advance follows from the Souveno current account after our founder's sign-off.\n\n"
            f"Regards,\n{p['contact_name']}\n{p['designation']}, {p['legal_name']}\nGSTIN {p['gstin']} · {p['phone']} · {p['email']}")

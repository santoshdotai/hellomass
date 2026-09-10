"""Propose → approve → execute.

The agent never spends money on its own. It PROPOSES a booking with the
amount worked out (stall advance = 50% of sqm x rate + 18% GST, flights from
the fare range, hotel from the picked tier), a human APPROVES with one tap on
the phone dashboard, and only then an executor runs:

  razorpayx  bank payout to the organiser (needs RAZORPAYX_* settings and a
             saved fund account for the payee)
  duffel     flight ticketing via the Duffel API (needs DUFFEL_ACCESS_TOKEN;
             a test token creates test orders, a live token issues real ones)
  email      sends the space-application / confirmation email
  manual     no rail configured: produces a payment instruction (UPI / NEFT /
             organiser link) for the human to complete

Everything is logged on the approval row, so the dashboard shows exactly
what was proposed, who approved it, and what happened.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from backend.core.expo import planner, scoring
from backend.core.expo.catalog import get_event, list_events
from backend.db import models
from config.settings import settings

GST = 0.18
ADVANCE_SHARE = 0.5


def _deadline(target: date, min_days_ahead: int = 7) -> str:
    """Never propose a decision date in the past: at least a week from today."""
    return max(target, date.today() + timedelta(days=min_days_ahead)).isoformat()


# ---------------------------------------------------------------- proposals
def stall_advance_proposal(ev: dict[str, Any], sqm: int | None = None, rate: int | None = None) -> dict[str, Any]:
    st = ev.get("stall", {})
    sqm = sqm or st.get("suggested_sqm") or 9
    rate = rate or st.get("shell_rate_inr_sqm") or 10000
    base = sqm * rate
    total = round(base * (1 + GST))
    advance = round(total * ADVANCE_SHARE)
    contact = ev.get("exhibitor_contact", {})
    start = date.fromisoformat(ev["start"])
    return {
        "kind": "stall_advance",
        "title": f"50% stall advance — {ev['name']} ({sqm} sqm shell)",
        "amount_inr": advance,
        "payee": contact.get("org") or ev.get("organiser", ""),
        "executor": "razorpayx" if settings.razorpayx_key_id else "manual",
        "deadline": _deadline(start - timedelta(days=90)),
        "details": {
            "sqm": sqm, "rate_inr_sqm": rate, "base_inr": base, "gst_pct": 18, "total_inr": total,
            "advance_share": ADVANCE_SHARE, "balance_inr": total - advance,
            "rate_status": "estimate — replace with the organiser's rate card before approving",
            "organiser_email": contact.get("email", ""), "organiser_phone": contact.get("phone", ""),
            "position_request": st.get("hall_hint", ""),
        },
    }


FLIGHT_PREFERRED_DAYS = 60   # domestic: book here if time permits (lowest fares)
FLIGHT_LATEST_DAYS = 30      # domestic hard rule
INTL_PREFERRED_DAYS = 90     # international: fares and visas both favour 90 days
INTL_LATEST_DAYS = 45        # international hard rule (leaves 3 weeks for the visa)
VISA_LEAD_DAYS = 21
INTERNATIONAL_AIRPORTS = {"DXB", "DWC", "AUH", "SHJ", "DOH", "RUH", "JED", "DMM", "MCT", "BAH", "KWI", "SIN", "KUL", "BKK", "LHR", "FRA"}
VISA_RULES = {  # Indian passport, business/visit; INR per person incl. service fees; lead time in working days
    "DXB": {"country": "UAE", "type": "UAE 30-day tourist/business e-visa", "inr_per_person": 9000, "lead_days": 7, "note": "Sponsored by the airline or a UAE agent; passport valid 6 months; usually issued in 3-5 working days."},
    "DWC": {"country": "UAE", "type": "UAE 30-day e-visa", "inr_per_person": 9000, "lead_days": 7, "note": "As DXB."},
    "AUH": {"country": "UAE", "type": "UAE 30-day e-visa", "inr_per_person": 9000, "lead_days": 7, "note": "As DXB."},
    "RUH": {"country": "Saudi Arabia", "type": "Saudi business visit e-visa (invitation from the organiser/host company)", "inr_per_person": 14000, "lead_days": 14, "note": "Needs an organiser invitation letter; apply 4-6 weeks out."},
    "JED": {"country": "Saudi Arabia", "type": "Saudi business visit e-visa", "inr_per_person": 14000, "lead_days": 14, "note": "As RUH."},
    "DOH": {"country": "Qatar", "type": "Qatar Hayya / visa on arrival for Indian passport (check current rule)", "inr_per_person": 3000, "lead_days": 5, "note": "Confirm current entry rule 6 weeks out."},
}


def is_international(airport: str | None) -> bool:
    return bool(airport) and airport.upper() in INTERNATIONAL_AIRPORTS


def flight_booking_window(depart: date, today: date | None = None, international: bool = False) -> dict[str, Any]:
    """Policy: domestic — book >= 30 days before departure, 60+ when possible.
    International — book >= 45 days before, 90+ when possible (fares + visa)."""
    today = today or date.today()
    pref_days, late_days = (INTL_PREFERRED_DAYS, INTL_LATEST_DAYS) if international else (FLIGHT_PREFERRED_DAYS, FLIGHT_LATEST_DAYS)
    preferred = depart - timedelta(days=pref_days)
    latest = depart - timedelta(days=late_days)
    days_left = (depart - today).days
    if days_left >= pref_days:
        status, advice = "ideal", f"Book by {preferred.isoformat()} for the lowest fares ({pref_days}+ days out)."
    elif days_left >= late_days:
        status, advice = "urgent", f"Inside the {pref_days}-day window; book now, hard deadline {latest.isoformat()} ({late_days} days before)."
    elif days_left > 0:
        status, advice = "late", f"Past the {late_days}-day rule ({latest.isoformat()}); book immediately, fares rise daily."
    else:
        status, advice = "past", "Departure date has passed."
    return {"preferred_by": preferred.isoformat(), "latest_by": latest.isoformat(), "days_to_departure": days_left,
            "status": status, "advice": advice, "international": international,
            "policy": (f"international: book >= {INTL_LATEST_DAYS} days before departure; >= {INTL_PREFERRED_DAYS} days when time permits"
                       if international else "book >= 30 days before departure; >= 60 days when time permits")}


def visa_proposal(ev: dict[str, Any], travellers: int = 2) -> dict[str, Any] | None:
    airport = (ev.get("travel") or {}).get("airport")
    rule = VISA_RULES.get((airport or "").upper())
    if not rule:
        return None
    tp = planner.travel_plan(ev, travellers)
    depart = date.fromisoformat(tp["outbound"]["date"])
    apply_by = depart - timedelta(days=VISA_LEAD_DAYS)
    return {
        "kind": "visa",
        "title": f"{rule['type']} x{travellers} — {ev['name']}",
        "amount_inr": rule["inr_per_person"] * travellers,
        "payee": f"{rule['country']} visa (via airline / agent)",
        "executor": "manual",
        "deadline": _deadline(apply_by, min_days_ahead=2),
        "details": {"country": rule["country"], "visa_type": rule["type"], "travellers": travellers, "apply_by": apply_by.isoformat(),
                    "lead_days": rule["lead_days"], "depart": depart.isoformat(), "note": rule["note"],
                    "documents": ["passport (6 months validity, 2 blank pages)", "photo 4.3x5.5 cm white background", "return ticket", "hotel booking", "organiser invitation / exhibitor badge confirmation"]},
    }


def flight_proposal(ev: dict[str, Any], travellers: int = 2) -> dict[str, Any] | None:
    tp = planner.travel_plan(ev, travellers)
    if not tp.get("needs_travel"):
        return None
    lo, hi = ev["travel"]["flight_oneway_inr"]
    est = round((lo + hi) / 2 * 2 * travellers)
    depart = date.fromisoformat(tp["outbound"]["date"])
    intl = is_international(ev["travel"].get("airport"))
    window = flight_booking_window(depart, international=intl)
    # decide-by = the 60-day mark when still ahead, otherwise as soon as possible (2 days)
    deadline = _deadline(date.fromisoformat(window["preferred_by"]), min_days_ahead=2)
    if window["status"] in ("urgent", "late"):
        deadline = _deadline(date.today(), min_days_ahead=1)
    return {
        "kind": "flight",
        "title": f"Flights {tp['outbound']['route']} {tp['outbound']['date']} / return {tp['return']['date']} x{travellers} — {ev['name']}",
        "amount_inr": est,
        "payee": "Airline (via Duffel)" if settings.duffel_access_token else "Airline / OTA",
        "executor": "duffel" if settings.duffel_access_token else "manual",
        "deadline": deadline,
        "details": {
            "booking_window": window,
            "international": intl,
            "passengers_note": "Automated ticketing needs DUFFEL_PASSENGERS_JSON (given_name, family_name, born_on, gender, phone, email" + (", passport number/expiry/nationality)" if intl else ")"),
            "origin": tp["outbound"]["route"].split(" -> ")[0], "destination": tp["outbound"]["route"].split(" -> ")[1],
            "depart": tp["outbound"]["date"], "return": tp["return"]["date"], "travellers": travellers,
            "fare_oneway_inr": [lo, hi], "cabin": "economy", "preference": "arrive evening before; return after 19:00",
            "links": {"outbound": tp["outbound"]["links"], "return": tp["return"]["links"]},
        },
    }


def hotel_proposal(ev: dict[str, Any], tier: str = "mid") -> dict[str, Any] | None:
    tp = planner.travel_plan(ev)
    if not tp.get("needs_travel"):
        return None
    picks = ev["travel"].get("hotels", [])
    pick = next((h for h in picks if h["tier"] == tier), picks[0] if picks else None)
    if not pick:
        return None
    nights = tp["hotel"]["nights"]
    est = round((pick["inr_night"][0] + pick["inr_night"][1]) / 2 * nights)
    return {
        "kind": "hotel",
        "title": f"Hotel {pick['name']} x{nights} nights — {ev['name']}",
        "amount_inr": est,
        "payee": pick["name"],
        "executor": "manual",
        "deadline": _deadline(date.fromisoformat(tp["hotel"]["checkin"]) - timedelta(days=14)),
        "details": {"hotel": pick, "checkin": tp["hotel"]["checkin"], "checkout": tp["hotel"]["checkout"], "nights": nights,
                    "links": tp["hotel"]["links"], "alternatives": [h["name"] for h in picks if h is not pick]},
    }


def proposals_for_event(ev: dict[str, Any], mode: str | None = None) -> list[dict[str, Any]]:
    mode = mode or ev.get("mode", "visit")
    out = []
    if mode == "exhibit":
        out.append(stall_advance_proposal(ev))
    for p in (flight_proposal(ev), hotel_proposal(ev), visa_proposal(ev)):
        if p:
            out.append(p)
    return out


def propose(db: Session, ev: dict[str, Any], mode: str | None = None, horizon_days: int | None = None) -> list[models.ExpoApproval]:
    """Create proposals that don't already exist (same event + kind, not rejected)."""
    if horizon_days is not None:
        if date.fromisoformat(ev["start"]) - date.today() > timedelta(days=horizon_days):
            return []
    plan = db.query(models.ExpoEventPlan).filter_by(event_id=ev["id"]).first()
    if plan and plan.decision == "skip":
        return []
    if plan and plan.decision in ("attend", "exhibit"):
        mode = "exhibit" if plan.decision == "exhibit" else mode or ev.get("mode")
    created = []
    for p in proposals_for_event(ev, mode):
        exists = db.query(models.ExpoApproval).filter(models.ExpoApproval.event_id == ev["id"], models.ExpoApproval.kind == p["kind"],
                                                       models.ExpoApproval.status != "rejected").first()
        if exists:
            continue
        row = models.ExpoApproval(event_id=ev["id"], kind=p["kind"], title=p["title"], amount_inr=p["amount_inr"], payee=p["payee"],
                                  executor=p["executor"], details_json=json.dumps(p["details"]),
                                  deadline=datetime.fromisoformat(p["deadline"]) if p.get("deadline") else None)
        db.add(row)
        created.append(row)
    db.commit()
    for r in created:
        db.refresh(r)
    return created


def propose_all(db: Session, horizon_days: int = 90) -> list[models.ExpoApproval]:
    created = []
    for ev in list_events():
        created += propose(db, ev, horizon_days=horizon_days)
    return created


# ---------------------------------------------------------------- execution
def _razorpayx_payout(row: models.ExpoApproval, details: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover - network
    import requests

    fund_account_id = details.get("fund_account_id")
    if not (settings.razorpayx_key_id and settings.razorpayx_key_secret and settings.razorpayx_account_number and fund_account_id):
        return {"ok": False, "mode": "manual", "reason": "RazorpayX keys or the payee's fund_account_id are missing; pay manually.",
                "instruction": _manual_instruction(row, details)}
    body = {"account_number": settings.razorpayx_account_number, "fund_account_id": fund_account_id, "amount": row.amount_inr * 100,
            "currency": "INR", "mode": details.get("payout_mode", "NEFT"), "purpose": "vendor bill",
            "queue_if_low_balance": True, "reference_id": row.approval_uid, "narration": (row.title[:30])}
    r = requests.post("https://api.razorpay.com/v1/payouts", json=body, timeout=30,
                      auth=(settings.razorpayx_key_id, settings.razorpayx_key_secret))
    ok = r.status_code < 300
    return {"ok": ok, "mode": "razorpayx", "status_code": r.status_code, "response": r.json() if r.content else {}}


def _duffel_order(row: models.ExpoApproval, details: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover - network
    """Search offers and hold/issue the cheapest matching one. Duffel test tokens
    create sandbox orders; live tokens issue real tickets and charge the Duffel balance."""
    import requests

    if not settings.duffel_access_token:
        return {"ok": False, "mode": "manual", "reason": "DUFFEL_ACCESS_TOKEN not set", "instruction": _manual_instruction(row, details)}
    h = {"Authorization": f"Bearer {settings.duffel_access_token}", "Duffel-Version": "v2", "Content-Type": "application/json", "Accept": "application/json"}
    pax = [{"type": "adult"} for _ in range(int(details.get("travellers", 1)))]
    req = {"data": {"slices": [{"origin": details["origin"], "destination": details["destination"], "departure_date": details["depart"]},
                               {"origin": details["destination"], "destination": details["origin"], "departure_date": details["return"]}],
                    "passengers": pax, "cabin_class": details.get("cabin", "economy"), "max_connections": 0}}
    r = requests.post("https://api.duffel.com/air/offer_requests?return_offers=true", json=req, headers=h, timeout=60)
    if r.status_code >= 300:
        return {"ok": False, "mode": "duffel", "status_code": r.status_code, "response": r.json()}
    offers = sorted(r.json()["data"].get("offers", []), key=lambda o: float(o["total_amount"]))
    if not offers:
        return {"ok": False, "mode": "duffel", "reason": "no offers"}
    offer = offers[0]
    if float(offer["total_amount"]) > row.amount_inr * 1.25:
        return {"ok": False, "mode": "duffel", "reason": f"cheapest offer {offer['total_amount']} {offer['total_currency']} exceeds approved budget by >25%",
                "offer_id": offer["id"]}
    passengers = details.get("passengers") or []
    if not passengers and settings.duffel_passengers_json:
        try:
            passengers = json.loads(settings.duffel_passengers_json)[: len(pax)]
        except json.JSONDecodeError:
            passengers = []
    if len(passengers) != len(pax):
        return {"ok": False, "mode": "duffel", "reason": "passenger details (given_name, family_name, born_on, gender, phone, email) missing in details.passengers",
                "offer_id": offer["id"], "offer_total": offer["total_amount"]}
    order = {"data": {"type": "instant", "selected_offers": [offer["id"]], "payments": [{"type": "balance", "amount": offer["total_amount"], "currency": offer["total_currency"]}],
                      "passengers": [{**p, "id": op["id"]} for p, op in zip(passengers, offer["passengers"])]}}
    r2 = requests.post("https://api.duffel.com/air/orders", json=order, headers=h, timeout=60)
    return {"ok": r2.status_code < 300, "mode": "duffel", "status_code": r2.status_code, "response": r2.json(), "offer_total": offer["total_amount"]}


def _manual_instruction(row: models.ExpoApproval, details: dict[str, Any]) -> str:
    if row.kind == "stall_advance":
        return (f"Pay ₹{row.amount_inr:,} to {row.payee} against their proforma invoice (NEFT/UPI details come with the space "
                f"application). Reference: {row.approval_uid}. Email: {details.get('organiser_email', '')}.")
    if row.kind == "flight":
        return f"Book via {details.get('links', {}).get('outbound', {}).get('google_flights', 'Google Flights')} within budget ₹{row.amount_inr:,}."
    if row.kind == "hotel":
        return f"Book {details.get('hotel', {}).get('name', 'the hotel')} {details.get('checkin')} → {details.get('checkout')} via {details.get('links', {}).get('google_hotels', '')}."
    if row.kind == "visa":
        return f"Apply for the {details.get('visa_type')} by {details.get('apply_by')} ({details.get('lead_days')} working days); {details.get('note', '')}"
    return f"Complete manually. Reference {row.approval_uid}."


def execute(db: Session, row: models.ExpoApproval) -> models.ExpoApproval:
    if row.status != "approved":
        raise ValueError("only approved items can be executed")
    details = json.loads(row.details_json or "{}")
    try:
        if row.executor == "razorpayx":
            result = _razorpayx_payout(row, details)
        elif row.executor == "duffel":
            result = _duffel_order(row, details)
        else:
            result = {"ok": False, "mode": "manual", "instruction": _manual_instruction(row, details)}
    except Exception as exc:  # network / provider failure
        logger.exception("approval execution failed")
        result = {"ok": False, "mode": row.executor, "error": str(exc)}
    row.execution_json = json.dumps(result)
    row.executed_at = datetime.utcnow()
    row.status = "executed" if result.get("ok") else ("approved" if result.get("mode") == "manual" else "failed")
    db.commit()
    db.refresh(row)
    return row


def to_dict(row: models.ExpoApproval) -> dict[str, Any]:
    ev = get_event(row.event_id) or {}
    return {
        "id": row.id, "approval_uid": row.approval_uid, "event_id": row.event_id, "event_name": ev.get("name", row.event_id),
        "kind": row.kind, "title": row.title, "amount_inr": row.amount_inr, "currency": row.currency, "payee": row.payee,
        "details": json.loads(row.details_json or "{}"), "status": row.status, "executor": row.executor,
        "execution": json.loads(row.execution_json or "{}"),
        "deadline": row.deadline.isoformat() if row.deadline else None,
        "proposed_at": row.proposed_at.isoformat() if row.proposed_at else None,
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        "executed_at": row.executed_at.isoformat() if row.executed_at else None,
        "notes": row.notes,
        "manual_instruction": _manual_instruction(row, json.loads(row.details_json or "{}")),
    }

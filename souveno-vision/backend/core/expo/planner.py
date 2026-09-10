"""Attend-everything planner: resolves date clashes into a day-by-day
itinerary, builds flight/hotel booking links, exports an ICS calendar and
produces the auto-fill profile used by the registration form filler."""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import quote_plus

from backend.core.expo.catalog import list_events, meta
from backend.core.expo.scoring import evaluate

HOME_AIRPORT = "HYD"

SOUVENO_PROFILE = {
    "company": "Souveno AI",
    "legal_name": "Souveno AI",
    "website": "https://souveno.ai",
    "alt_website": "https://souveno.in",
    "email": "souveno30@gmail.com",
    "phone": "+91 86393 32232",
    "contact_name": "Santosh Padmaa",
    "designation": "Founder & CEO",
    "city": "Hyderabad",
    "state": "Telangana",
    "country": "India",
    "industry": "AI software / business automation",
    "products": "WhatsApp AI sales engine (enquiry -> stock -> GST quotation PDF -> payment), custom AI agents, agentic operating system, Vision AI",
    "description": "Souveno builds Intelligent Business Operating Systems: Communication AI, Workflow AI and Vision AI that turn WhatsApp enquiries from manufacturers and distributors into quotations, orders and payments automatically.",
    "target_visitors": "Manufacturers, wholesalers and distributors with 20-300 WhatsApp quote requests a day",
    "stall_preference": "Corner stall, 9-12 sqm shell scheme, main aisle near entrance",
    "gstin": "36BDNPP2011D2ZV",
    "address": "",
    "calendly": "https://calendly.com/souveno30",
}


def _d(s: str) -> date:
    return date.fromisoformat(s)


def flight_links(origin: str, dest: str, day: date) -> dict[str, str]:
    dmy = day.strftime("%d/%m/%Y")
    iso = day.isoformat()
    return {
        "google_flights": f"https://www.google.com/travel/flights?q={quote_plus(f'flights from {origin} to {dest} on {iso}')}",
        "makemytrip": f"https://www.makemytrip.com/flight/search?itinerary={origin}-{dest}-{dmy}&tripType=O&paxType=A-1_C-0_I-0&cabinClass=E",
        "ixigo": f"https://www.ixigo.com/search/result/flight?from={origin}&to={dest}&date={day.strftime('%d%m%Y')}&adults=1&children=0&infants=0&class=e",
    }


def hotel_links(venue: str, city: str, checkin: date, checkout: date) -> dict[str, str]:
    q = quote_plus(f"hotels near {venue} {city}")
    return {
        "google_hotels": f"https://www.google.com/travel/hotels?q={q}&checkin={checkin.isoformat()}&checkout={checkout.isoformat()}",
        "makemytrip": f"https://www.makemytrip.com/hotels/hotel-listing/?checkin={checkin.strftime('%m%d%Y')}&checkout={checkout.strftime('%m%d%Y')}&city={quote_plus(city)}&roomStayQualifier=2e0e&searchText={q}",
    }


def travel_plan(ev: dict[str, Any], travellers: int = 2) -> dict[str, Any]:
    start, end = _d(ev["start"]), _d(ev["end"])
    airport = ev.get("travel", {}).get("airport")
    if not airport:
        return {"needs_travel": False, "note": "Home city — no flight or hotel needed."}
    depart = start - timedelta(days=1)
    ret = end
    return {
        "needs_travel": True,
        "outbound": {"date": depart.isoformat(), "route": f"{HOME_AIRPORT} -> {airport}", "arrive_by": "evening", "links": flight_links(HOME_AIRPORT, airport, depart)},
        "return": {"date": ret.isoformat(), "route": f"{airport} -> {HOME_AIRPORT}", "depart_after": "19:00", "links": flight_links(airport, HOME_AIRPORT, ret)},
        "hotel": {"checkin": depart.isoformat(), "checkout": ret.isoformat(), "nights": (ret - depart).days,
                   "picks": ev.get("travel", {}).get("hotels", []), "links": hotel_links(ev["venue"], ev["city"], depart, ret)},
        "travellers": travellers,
        "fare_estimate_oneway_inr": ev.get("travel", {}).get("flight_oneway_inr"),
    }


def clashes(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for i, a in enumerate(events):
        for b in events[i + 1:]:
            if _d(a["start"]) <= _d(b["end"]) and _d(b["start"]) <= _d(a["end"]):
                out.append({"a": a["id"], "b": b["id"], "overlap_start": max(a["start"], b["start"]), "overlap_end": min(a["end"], b["end"])})
    return out


def attend_all_itinerary(events: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Assign every calendar day to at most one event so that all events are
    attended. Greedy day-by-day choice weighted by: event score, fair share of
    days already given, and a continuity bonus for staying in the same city
    (fewer flights). Every event keeps at least one day: on its last day an
    event that has had none wins outright (a home stall can be staffed by the
    CTO while the founder flies). Returns day slots ordered by date."""
    events = events or list_events()
    scored = {e["id"]: evaluate(e)["total_score"] for e in events}
    by_day: dict[date, list[dict[str, Any]]] = {}
    for e in events:
        d = _d(e["start"])
        while d <= _d(e["end"]):
            by_day.setdefault(d, []).append(e)
            d += timedelta(days=1)
    assigned: dict[date, dict[str, Any]] = {}
    days_given: dict[str, int] = {e["id"]: 0 for e in events}
    prev_city: str | None = None
    for d in sorted(by_day):
        cands = by_day[d]
        starving = [c for c in cands if days_given[c["id"]] == 0 and d == _d(c["end"])]
        if starving:
            pick = max(starving, key=lambda c: scored[c["id"]])
        else:
            def weight(c: dict[str, Any]) -> float:
                length = (_d(c["end"]) - _d(c["start"])).days + 1
                fairness = days_given[c["id"]] / length
                continuity = 0.5 if c["city"] == prev_city else 0.0
                return scored[c["id"]] / 100.0 - fairness + continuity
            pick = max(cands, key=weight)
        assigned[d] = pick
        days_given[pick["id"]] += 1
        prev_city = pick["city"]
    slots = []
    prev_id = None
    for d in sorted(assigned):
        e = assigned[d]
        others = [c["id"] for c in by_day[d] if c["id"] != e["id"]]
        same_venue = [c["id"] for c in by_day[d] if c["id"] != e["id"] and c["city"] == e["city"] and c.get("venue_area") == e.get("venue_area")]
        slots.append({
            "date": d.isoformat(),
            "weekday": d.strftime("%a"),
            "event_id": e["id"],
            "event": e["name"],
            "city": e["city"],
            "venue": e["venue"],
            "also_running": others,
            "same_venue": same_venue,
            "travel_day_before": prev_id != e["id"] and bool(e.get("travel", {}).get("airport")),
        })
        prev_id = e["id"]
    return slots


def _ics_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def to_ics(events: list[dict[str, Any]] | None = None, include_travel: bool = True) -> str:
    events = events or list_events()
    now = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Souveno AI//Expo Agent//EN", "CALSCALE:GREGORIAN",
             "X-WR-CALNAME:Souveno Expo Calendar 2026-27"]
    for e in events:
        ev = evaluate(e)
        uid = hashlib.md5(e["id"].encode()).hexdigest() + "@souveno.ai"
        end_excl = (_d(e["end"]) + timedelta(days=1)).strftime("%Y%m%d")
        desc = (f"{ev['stars_label']} stars | {e['mode'].upper()} | {e['category']}\\n"
                f"{e['why']}\\nVenue: {e['venue']}, {e['venue_area']}\\n"
                f"Client probability: {ev['funnel']['client_probability_pct']}% | Budget INR {ev['budget']['total_inr'][0]:,}-{ev['budget']['total_inr'][1]:,}\\n"
                f"Stall: {e['stall']['recommend']}\\n{e['website']}")
        lines += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{now}",
                  f"DTSTART;VALUE=DATE:{_d(e['start']).strftime('%Y%m%d')}", f"DTEND;VALUE=DATE:{end_excl}",
                  f"SUMMARY:{_ics_escape(('[TENTATIVE] ' if e.get('tentative') else '') + e['name'] + ' — ' + e['city'])}",
                  f"LOCATION:{_ics_escape(e['venue'] + ', ' + e['city'])}",
                  f"DESCRIPTION:{_ics_escape(desc)}", f"URL:{e['website']}", "END:VEVENT"]
        if include_travel and e.get("travel", {}).get("airport"):
            tp = travel_plan(e)
            for leg in ("outbound", "return"):
                d = _d(tp[leg]["date"])
                lines += ["BEGIN:VEVENT", f"UID:{uid}-{leg}", f"DTSTAMP:{now}",
                          f"DTSTART;VALUE=DATE:{d.strftime('%Y%m%d')}", f"DTEND;VALUE=DATE:{(d + timedelta(days=1)).strftime('%Y%m%d')}",
                          f"SUMMARY:{_ics_escape('✈ ' + tp[leg]['route'] + ' — ' + e['name'])}",
                          f"DESCRIPTION:{_ics_escape(tp[leg]['links']['google_flights'])}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def autofill_profile(overrides: dict[str, str] | None = None) -> dict[str, str]:
    p = dict(SOUVENO_PROFILE)
    if overrides:
        p.update({k: v for k, v in overrides.items() if v is not None})
    return p


def registration_answers(ev: dict[str, Any], profile: dict[str, str] | None = None) -> dict[str, str]:
    """Pre-written answers for the fields every organiser's exhibitor/visitor
    form asks; paste or let the bookmarklet fill them."""
    p = profile or autofill_profile()
    mode = ev.get("mode", "visit")
    return {
        "participation_type": "Exhibitor" if mode == "exhibit" else "Trade visitor",
        "company_name": p["company"],
        "contact_person": p["contact_name"],
        "designation": p["designation"],
        "email": p["email"],
        "mobile": p["phone"],
        "website": p["website"],
        "city": p["city"],
        "state": p["state"],
        "country": p["country"],
        "gstin": p["gstin"],
        "address": p["address"],
        "nature_of_business": "Software / IT — AI automation for manufacturers and distributors",
        "products_to_display": p["products"],
        "company_profile": p["description"],
        "stall_size_sqm": str(ev.get("stall", {}).get("suggested_sqm", 9) or 9),
        "stall_type": "Shell scheme, corner (two open sides)",
        "stall_location_preference": ev.get("stall", {}).get("hall_hint", ""),
        "purpose_of_visit": "Sourcing AI/automation partners; meeting distributors and manufacturers",
        "how_did_you_hear": "Website",
        "interested_in": ev.get("category", ""),
    }


def catalog_summary() -> dict[str, Any]:
    events = list_events()
    ranked = sorted(({**e, "evaluation": evaluate(e)} for e in events), key=lambda x: (-x["evaluation"]["total_score"], x["start"]))
    return {"meta": meta(), "count": len(events), "events": ranked, "clashes": clashes(events), "itinerary": attend_all_itinerary(events)}

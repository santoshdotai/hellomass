"""Voice commands. The browser turns speech into text (Web Speech API); this module turns the text
into one intent and a spoken reply. Same grammar runs client-side on the phone dashboard.

Examples that work:
  "book tickets to ELECRAMA"          -> approves the flight proposal (manual mode: opens Skyscanner; automate: agent books)
  "book hotel for Plastivision"       -> approves the hotel proposal
  "book the stall at Fastener Fair"   -> approves the stall advance
  "mark Hardware Fair flight done PNR ABC123"
  "when is IMTEX" / "dates of Big 5"  -> speaks the dates and city
  "how good is WAREMAT for us"        -> stars and why
  "what does ELECRAMA cost"           -> budget, stall advance, subsidy
  "what's coming in two months"       -> finance summary for that horizon
  "next event"                        -> the next show and days away
  "subsidy deadlines"                 -> next apply-by dates
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from backend.core.expo import finance, scoring, subsidy
from backend.core.expo.catalog import list_events

ALIASES = {
    "elecrama": "elecrama-2027", "plastivision": "plastivision-2027", "fastener": "fastener-fair-india-2027", "hardware fair": "hardware-fair-india-2026",
    "hardware": "hardware-fair-india-2026", "big 5 saudi": "big5-saudi-2027", "big five saudi": "big5-saudi-2027", "riyadh": "big5-saudi-2027",
    "big 5": "big5-global-2026", "big five": "big5-global-2026", "gitex": "gitex-global-2026", "imtex": "imtex-2027", "warehousing": "india-warehousing-show-2027",
    "ifsec": "ifsec-india-2026", "intersec": "intersec-dubai-2027", "gulfood": "gulfood-manufacturing-2026", "papexpo": "papexpo-2026", "paper expo": "papexpo-2026",
    "waremat": "waremat-2026", "acetech": "acetech-hyderabad-2027", "automation expo": "automation-expo-2027", "robotics": "india-automation-robotics-2027",
    "engiexpo pune": "engiexpo-pune-2026", "engi expo pune": "engiexpo-pune-2026", "pune": "engiexpo-pune-2026", "engiexpo ahmedabad": "engiexpo-ahmedabad-2026",
    "ahmedabad": "engiexpo-ahmedabad-2026", "surat": "engiexpo-surat-2027", "jaipur": "engiexpo-jaipur-2027", "indexpo mumbai": "indexpo-mumbai-2027",
    "indexpo hyderabad": "indexpo-hyderabad-2027", "indexpo": "indexpo-hyderabad-2027", "pharma": "india-pharma-expo-2027", "mahakumbh": "startup-mahakumbh-2027",
    "startup": "startup-mahakumbh-2027", "convergence": "convergence-india-2027", "middle east energy": "middle-east-energy-2027", "energy": "middle-east-energy-2027",
    "gulf print": "gulf-print-pack-2027", "bengaluru tech": "bts-2026", "bangalore tech": "bts-2026", "tech summit": "bts-2026",
}
HORIZON_WORDS = {"week": "w", "weeks": "w", "month": "m", "months": "m"}
NUM = {"one": 1, "a": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", t.lower()).strip()


def find_event(text: str) -> dict[str, Any] | None:
    t = _norm(text)
    for alias in sorted(ALIASES, key=len, reverse=True):
        if alias in t:
            eid = ALIASES[alias]
            return next((e for e in list_events() if e["id"] == eid), None)
    for e in list_events():  # fall back to any two words of the name
        words = [w for w in _norm(e["name"]).split() if len(w) > 3]
        if sum(1 for w in words if w in t) >= 2:
            return e
    return None


def _horizon(text: str) -> str | None:
    t = _norm(text)
    m = re.search(r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|a)\s+(weeks?|months?)", t)
    if not m:
        if "this week" in t:
            return "1w"
        if "this month" in t:
            return "1m"
        return None
    n = int(m.group(1)) if m.group(1).isdigit() else NUM[m.group(1)]
    unit = HORIZON_WORDS[m.group(2)]
    key = f"{n}{unit}"
    return key if any(k == key for k, _, _ in finance.HORIZONS) else ("3w" if unit == "w" else "12m")


def _fmt_date(s: str) -> str:
    d = date.fromisoformat(s)
    return d.strftime("%-d %B %Y")


def parse(text: str, today: date | None = None) -> dict[str, Any]:
    """Return {"intent", "event_id", "kind", "reference", "horizon", "reply", "action"}; action tells the client what to do."""
    today = today or date.today()
    t = _norm(text)
    ev = find_event(t)
    out: dict[str, Any] = {"text": text, "intent": "unknown", "event_id": ev["id"] if ev else None, "event_name": ev["name"] if ev else None, "action": None, "reply": ""}

    if re.search(r"\b(done|paid|booked)\b", t) and ev:
        kind = "hotel" if "hotel" in t else "stall_advance" if "stall" in t else "visa" if "visa" in t else "flight"
        ref = re.search(r"(?:pnr|utr|reference|confirmation|number)\s+([a-z0-9]{5,})", t)
        out.update({"intent": "mark_done", "kind": kind, "reference": ref.group(1).upper() if ref else "", "action": "mark_done",
                    "reply": f"Marked the {kind.replace('_', ' ')} for {ev['name']} as done" + (f" with reference {ref.group(1).upper()}" if ref else "") + "."})
        return out
    if re.search(r"\b(book|reserve|approve|confirm)\b", t) and ev:
        kind = "hotel" if re.search(r"hotel|room|stay", t) else "stall_advance" if re.search(r"stall|booth|space|stand", t) else "visa" if "visa" in t else "flight"
        what = {"flight": "flights", "hotel": "hotel", "stall_advance": "stall advance", "visa": "visa"}[kind]
        out.update({"intent": "approve", "kind": kind, "action": "approve",
                    "reply": f"Approving the {what} for {ev['name']}. In manual mode I open the pre-filled search for you to pay; in automate mode the agent books it and reads the confirmation e-mail."})
        return out
    if ev and re.search(r"\b(when|date|dates|which day|start)\b", t):
        e = scoring.evaluate(ev)
        out.update({"intent": "dates", "action": "speak", "reply": f"{ev['name']} runs from {_fmt_date(ev['start'])} to {_fmt_date(ev['end'])} at {ev['venue']}, {ev['city']}. That is {(date.fromisoformat(ev['start']) - today).days} days away. It is {'an exhibit' if ev['mode'] == 'exhibit' else 'a visit'} rated {e['stars']:.1f} stars."})
        return out
    if ev and re.search(r"\b(cost|budget|price|how much|spend|expensive)\b", t):
        e = scoring.evaluate(ev); b = e["budget"]; sub = subsidy.for_event(ev, today)
        cost = b["total_inr"] if isinstance(b["total_inr"], list) else [b["total_inr"], b["total_inr"]]
        out.update({"intent": "cost", "action": "speak", "reply": f"{ev['name']}: about {cost[0]:,} to {cost[1]:,} rupees for two people" + (f", including a {b['stall_sqm']} square metre stall at {b['stall_inr']:,}" if b.get("stall_sqm") else "") + f". Subsidy money back estimated at {sub['estimated_refund_inr'][0]:,} to {sub['estimated_refund_inr'][1]:,} rupees. Expected {e['funnel']['paid_pilots'][0]} to {e['funnel']['paid_pilots'][1]} paying clients."})
        return out
    if ev and re.search(r"\b(footfall|visitors|crowd|how many people)\b", t):
        x = scoring.explain(ev)
        out.update({"intent": "footfall", "action": "speak", "reply": f"{ev['name']}: {x['footfall_expected']}"})
        return out
    if ev and re.search(r"\b(subsid|money back|reimburse|early bird|deadline)\b", t):
        sub = subsidy.for_event(ev, today)
        lines = [f"{s['name']}: apply by {s['apply_by']}" if s["apply_by"] else f"{s['name']}: claim after the show" for s in sub["schemes"]]
        out.update({"intent": "subsidy", "action": "speak", "reply": f"{ev['name']}: {sub['headline']} " + " ".join(lines) + f" Early bird: {sub['early_bird']['deadline'] or 'not published yet'}."})
        return out
    if ev and re.search(r"\b(good|rating|stars|score|worth|should we|why)\b", t):
        x = scoring.explain(ev); e = scoring.evaluate(ev)
        out.update({"intent": "rating", "action": "speak", "reply": f"{ev['name']} is {x['headline']}. Lead with {'Vision AI' if e['lead_product'] == 'vision_ai' else 'both products' if e['lead_product'] == 'both' else 'the WhatsApp quote desk'}. {x['lines'][0]}"})
        return out
    if ev and re.search(r"\b(lead|leads|clients|conversion)\b", t):
        e = scoring.evaluate(ev); f = e["funnel"]
        out.update({"intent": "leads", "action": "speak", "reply": f"{ev['name']}: expected {f['leads'][0]} to {f['leads'][1]} leads, {f['demos'][0]} to {f['demos'][1]} demos and {f['paid_pilots'][0]} to {f['paid_pilots'][1]} paying clients; {f['client_probability_pct']}% chance of at least one."})
        return out
    if ev and re.search(r"\b(stall|booth|where|hall|sit)\b", t):
        st = ev.get("stall") or {}
        out.update({"intent": "stall", "action": "speak", "reply": f"{ev['name']}: {st.get('recommend', '')}. Position: {st.get('hall_hint', '')}."})
        return out
    h = _horizon(t)
    if h and re.search(r"\b(coming|upcoming|what|which|show|shows|events|expo|in|next|financ|profit|loss|p and l)\b", t):
        r = finance.report(h, today); tt = r["totals"]
        names = ", ".join(x["name"] for x in (r["exhibits"] + r["visits"])[:6])
        out.update({"intent": "horizon", "horizon": h, "action": "open_finance",
                    "reply": f"{r['horizon_label'].capitalize()}: {tt['all']['shows']} shows, {tt['exhibits']['shows']} exhibits and {tt['visits']['shows']} visits. Cost {tt['all']['cost_inr'][0]:,} to {tt['all']['cost_inr'][1]:,} rupees, {tt['all']['leads'][0]} to {tt['all']['leads'][1]} leads, {tt['all']['conversions'][0]} to {tt['all']['conversions'][1]} clients, P and L {tt['all']['pl_inr'][0]:,} to {tt['all']['pl_inr'][1]:,} rupees." + (f" Shows: {names}." if names else "")})
        return out
    if re.search(r"\b(next|upcoming|coming up)\b", t):
        nxt = sorted((e for e in list_events() if date.fromisoformat(e["start"]) >= today), key=lambda e: e["start"])[:3]
        out.update({"intent": "next", "action": "speak", "reply": "Next: " + "; ".join(f"{e['name']} on {_fmt_date(e['start'])} in {e['city']}, {(date.fromisoformat(e['start']) - today).days} days away, {e['mode']}" for e in nxt) + "."})
        return out
    if re.search(r"\b(subsid|deadline|money back)\b", t):
        dl = subsidy.deadlines(today)[:5]
        out.update({"intent": "deadlines", "action": "speak", "reply": "Next subsidy deadlines: " + "; ".join(f"{d['event']} {d['what']} on {d['date']}, {d['days_left']} days" for d in dl) + "." if dl else "No subsidy deadlines in the next four months."})
        return out
    if re.search(r"\b(approvals?|waiting|pending|tap)\b", t):
        out.update({"intent": "approvals", "action": "open_approvals", "reply": "Opening the approvals waiting for your tap."})
        return out
    if re.search(r"\b(help|what can you do)\b", t):
        out.update({"intent": "help", "action": "speak", "reply": "Try: book tickets to ELECRAMA; book hotel for Plastivision; mark Hardware Fair flight done PNR ABC123; when is IMTEX; what does WAREMAT cost; what is coming in two months; next event; subsidy deadlines."})
        return out
    out["reply"] = "I did not catch a show name or a command. Say for example: book tickets to ELECRAMA, or when is Plastivision, or what is coming in two months."
    return out

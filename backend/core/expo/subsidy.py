"""Subsidies, reimbursements and early-bird deadlines per show.

Souveno AI is a Hyderabad-registered service MSE (GSTIN 36BDNPP2011D2ZV). The
scheme catalogue below is what the agent could verify from public sources on
10-11 Sept 2026; anything marked ``to_verify`` is re-checked by the 3-day
follow-up routine, which writes what it finds into the event's ``subsidy``
block in data/expo/events.json (early_bird_deadline, early_bird_note,
scheme_overrides, sources, last_checked, status, notes).

Rules of thumb the engine applies:
* PMS (domestic trade fairs) only helps when Souveno EXHIBITS; visiting has no
  stall rent to reimburse. Apply on my.msme.gov.in >= 30 days before the show,
  claim within 30 days after.
* Foreign fairs: the MSME International Cooperation scheme reimburses airfare
  and space rent, but only through a registered industry association's
  delegation (Souveno cannot apply alone). MAI works through an Export
  Promotion Council (ESC India for software) after 12 months of membership.
* Organiser early-bird deadlines are per show and usually not published a year
  out: ``null`` means "not published yet", never a guess.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from backend.core.expo.catalog import list_events

GULF_AIRPORTS = {"DXB", "DWC", "AUH", "SHJ", "RUH", "JED", "DMM", "DOH", "MCT", "BAH", "KWI"}

SCHEMES: dict[str, dict[str, Any]] = {
    "pms": {
        "name": "MSME Procurement & Marketing Support (PMS) scheme — domestic trade fairs",
        "authority": "Ministry of MSME (DC-MSME), apply on my.msme.gov.in",
        "who": "Udyam-registered micro or small enterprise (manufacturing or service). Souveno qualifies as a service MSE.",
        "benefit": "80% of stall space rent reimbursed (100% for SC/ST/women/NER/PwD/aspirational-district units), ceiling per enterprise per event ₹1.50 lakh in Metro/A-class cities, ₹1.00 lakh in B-class cities, ₹0.80 lakh elsewhere (incl. taxes); support is computed for up to 9 sqm; max two events per financial year. Verified 13 Sep 2026 from the revised (2021) PMS guidelines OM F.No. 5(1)/2021-2Z/PMS/SFC as reproduced by Vikaspedia, UP MSME 1-Connect, Stonemart and the Scribd copy of the DC-MSME OM (the ministry PDF is a scanned image; my.msme.gov.in is unreadable from the agent sandbox). The ₹30,000 + ₹15,000 figures are the superseded 2016 MATU text. ONLY fairs on the DC-MSME approved list (my.msme.gov.in → PMS → Trade Fairs Domestic) qualify; the Fair/Exhibition Selection Committee at DC-MSME decides that list.",
        "scope": "domestic_exhibit",
        "lead_days": 30,
        "claim_days_after": 30,
        "apply_rule": "First check the fair appears in the Trade Fairs Domestic list on my.msme.gov.in (Udyam login). If it does: apply online at least 30 days before the show (ni-msme says the PRISM pre-approval window opens 90 days before — apply as early as the portal allows) and submit the claim with stall-rent invoice, payment proof and photos within 30 days after it ends. If it does not: the organiser / industry association must get the fair approved by DC-MSME — ask them, and re-check the list every 3 days.",
        "link": "https://my.msme.gov.in/MyMsme/Reg/COM_Fair.aspx",
        "status": "confirmed",
        "fair_must_be_listed": True,
        "sources": ["https://en.vikaspedia.in/viewcontent/schemesall/schemes-for-entrepreneurs/procurement-and-marketing-support/procurement-marketing-support-to-msmes?lgn=en", "https://msme1connect.up.gov.in/Home/SchemesList/32", "https://www.stonemart-india.in/pms-scheme", "https://www.scribd.com/document/743420419/OM-PMS-Scheme-Guidelines", "https://ramp.msme.gov.in/ramp/sites/default/files/2026-05/PMS_Scheme_Guidelines_0.pdf", "https://schemesmsme.com/procurement-and-marketing-support-pms-msme-2025-26/", "https://msme.gov.in/1-marketing-promotion-schemes"],
    },
    "telangana": {
        "name": "Telangana MSME Policy 2024 — marketing / trade-fair assistance",
        "authority": "Industries & Commerce Dept, Telangana (TS-iPASS / District Industries Centre, Hyderabad)",
        "who": "MSMEs registered in Telangana with Udyam + TS-iPASS acknowledgement.",
        "benefit": "Reimbursement of stall rent for participation in national and international trade fairs (exact % and cap are in the operational guidelines under G.O.Ms. No. 16, Industries & Commerce (FP & MSME) Dept, 18 Sep 2024 — still being verified: the policy PDF and the TS-iPASS guidelines are unreadable from the agent sandbox; Startup Telangana separately lists up to 30% reimbursement of international trade-show marketing expenses).",
        "scope": "any_exhibit",
        "lead_days": 0,
        "claim_days_after": 90,
        "apply_rule": "Claim after the fair through the DIC with the rent invoice and participation certificate; the guidelines set the window.",
        "link": "https://ipass.telangana.gov.in/",
        "status": "to_verify",
        "sources": ["https://www.telangana.gov.in/wp-content/uploads/2024/09/Telangana-MSME-Policy-2024-English.pdf"],
    },
    "ic": {
        "name": "MSME International Cooperation (IC) scheme — foreign fairs",
        "authority": "Ministry of MSME, https://www.ic.msme.gov.in/",
        "who": "Registered industry associations / NSIC / EPC delegations; an MSE joins as a delegation member (Souveno cannot apply alone — join via FTCCI, TiE Hyderabad, EEPC or NSIC).",
        "benefit": "Economy airfare and stall space rent reimbursed to the delegation (micro units get the highest slab; slabs vary by year).",
        "scope": "international",
        "lead_days": 120,
        "claim_days_after": 30,
        "apply_rule": "The association applies in the ministry's call for proposals before the event. The last call (events 1 Jun – 30 Sep 2026) closed on 5 May 2026 17:30; no call for Oct 2026 – Mar 2027 events was visible on 13 Sep 2026 — the 3-day follow-up keeps watching ic.msme.gov.in.",
        "link": "https://www.ic.msme.gov.in/",
        "status": "to_verify",
        "sources": ["https://www.ic.msme.gov.in/", "https://msme.gov.in/international-cooperation"],
    },
    "mai": {
        "name": "Market Access Initiative (MAI) via an Export Promotion Council",
        "authority": "Department of Commerce; for software/SaaS the EPC is ESC India (escindia.in)",
        "who": "Exporters with 12+ months EPC membership and export turnover under ₹50 crore.",
        "benefit": "Up to two-thirds of airfare and stall space in the India pavilion of an approved fair abroad.",
        "scope": "international",
        "lead_days": 90,
        "claim_days_after": 30,
        "apply_rule": "Join ESC India now (12-month membership rule), then apply through the EPC about 90 days before each fair.",
        "link": "https://escindia.org/market-access-initiative-mai-scheme.html",
        "status": "needs_membership",
        "sources": ["https://escindia.org/market-access-initiative-mai-scheme.html"],
    },
    "startup": {
        "name": "Startup India / DPIIT subsidised startup pods",
        "authority": "DPIIT / organiser startup pavilion",
        "who": "DPIIT-recognised startups.",
        "benefit": "Free or heavily subsidised pod in the startup pavilion (Startup Mahakumbh, Bengaluru Tech Summit, Convergence India AI pavilion).",
        "scope": "startup_pavilion",
        "lead_days": 45,
        "claim_days_after": 0,
        "apply_rule": "Apply on the organiser's startup pavilion form; slots close about 45 days before.",
        "link": "https://www.startupindia.gov.in/",
        "status": "to_verify",
        "sources": [],
    },
}

STARTUP_SHOWS = {"startup-mahakumbh-2027", "bts-2026", "convergence-india-2027", "gitex-global-2026"}


PMS_CEILING_INR = {"metro_a": 150000, "b": 100000, "other": 80000}
_METRO_A_CITIES = {"hyderabad", "mumbai", "new delhi", "delhi", "greater noida", "noida", "gurugram", "bengaluru", "chennai", "kolkata", "ahmedabad", "pune"}
_B_CITIES = {"surat", "jaipur", "indore", "lucknow", "nagpur", "coimbatore", "kochi", "vadodara", "visakhapatnam", "bhopal"}


def _city_class(ev: dict[str, Any]) -> str:
    """City class for the PMS space-rent ceiling (Metro/A-class per the 2021 guidelines; NCR towns treated as Delhi)."""
    city = (ev.get("city") or "").strip().lower()
    if city in _METRO_A_CITIES:
        return "metro_a"
    if city in _B_CITIES:
        return "b"
    return "other"


def _d(s: str) -> date:
    return date.fromisoformat(s)


def _applicable(ev: dict[str, Any]) -> list[str]:
    airport = ((ev.get("travel") or {}).get("airport") or "").upper()
    intl = airport in GULF_AIRPORTS
    exhibit = ev.get("mode") == "exhibit"
    keys: list[str] = []
    if exhibit and not intl:
        keys.append("pms")
    if exhibit:
        keys.append("telangana")
    if intl and exhibit:
        keys += ["ic", "mai"]
    if ev["id"] in STARTUP_SHOWS:
        keys.append("startup")
    return keys


def _estimate_refund(ev: dict[str, Any], key: str) -> tuple[int, int] | None:
    st = ev.get("stall") or {}
    sqm = int(st.get("suggested_sqm") or 9)
    rate = int(st.get("shell_rate_inr_sqm") or 10000)
    rent = sqm * rate
    tr = ev.get("travel") or {}
    fare = tr.get("flight_oneway_inr") or [0, 0]
    airfare_two_pax = (fare[0] + fare[1]) * 2  # two travellers, return
    if key == "pms":
        cap = PMS_CEILING_INR.get(_city_class(ev), 80000)  # 2021 PMS guidelines: ₹1.5 L metro/A, ₹1.0 L B-class, ₹0.8 L other
        refund = min(cap, round(rent * 0.8))
        return (refund, refund)
    if key == "telangana":
        return (round(rent * 0.25), round(rent * 0.5))  # guideline range being verified
    if key == "ic":
        return (round(rent * 0.5), round(rent * 1.0 + airfare_two_pax * 0.5))
    if key == "mai":
        return (round((rent + airfare_two_pax) * 0.5), round((rent + airfare_two_pax) * 2 / 3))
    if key == "startup":
        return (0, rent)
    return None


def for_event(ev: dict[str, Any], today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    start = _d(ev["start"])
    override = ev.get("subsidy") or {}
    schemes = []
    for key in _applicable(ev):
        base = dict(SCHEMES[key])
        base.update(override.get("scheme_overrides", {}).get(key, {}))
        lead = int(base.get("lead_days") or 0)
        apply_by = (start - timedelta(days=lead)).isoformat() if lead else None
        claim_by = (_d(ev["end"]) + timedelta(days=int(base.get("claim_days_after") or 0))).isoformat() if base.get("claim_days_after") else None
        est = _estimate_refund(ev, key)
        days_left = (start - timedelta(days=lead) - today).days if lead else None
        status = base["status"]
        listing = None
        if base.get("fair_must_be_listed"):
            # "confirmed" only once the fair itself is on the DC-MSME approved list (per-event `subsidy.pms_listed`)
            listed = override.get("pms_listed", "unknown")
            checked = override.get("pms_list_checked") or override.get("last_checked")
            if listed == "yes":
                status, listing = "confirmed", {"state": "listed", "checked": checked, "note": f"On the DC-MSME approved list (checked {checked})."}
            elif listed == "no":
                status, listing = "fair_not_listed", {"state": "not_listed", "checked": checked, "note": f"Scheme rules confirmed, but this fair is NOT on the Trade Fairs Domestic list on my.msme.gov.in (checked {checked}). Nothing can be claimed unless the organiser gets it approved or it appears in a later list update."}
            else:
                status, listing = "check_list", {"state": "unknown", "checked": checked, "note": "Scheme rules confirmed; whether this fair is on the DC-MSME approved list has not been checked yet — look it up on my.msme.gov.in before counting on the money."}
        schemes.append({
            "key": key, "name": base["name"], "who": base["who"], "benefit": base["benefit"], "apply_rule": base["apply_rule"],
            "link": base["link"], "status": status, "listing": listing, "apply_by": apply_by, "claim_by": claim_by,
            "days_to_apply": days_left, "estimated_refund_inr": list(est) if est else None,
            "urgency": "late" if (days_left is not None and days_left < 0) else "soon" if (days_left is not None and days_left <= 30) else "ok",
        })
    # schemes cannot be stacked on the same stall rent: show the best single scheme's range
    money = [(s["status"] == "confirmed", s["estimated_refund_inr"]) for s in schemes if s["key"] in ("pms", "telangana", "ic", "mai") and s["estimated_refund_inr"] and s["status"] != "fair_not_listed"]
    best = max(money, key=lambda r: (r[0], r[1][1]))[1] if money else [0, 0]  # confirmed schemes first, then the largest
    total_lo, total_hi = best[0], best[1]
    pms_row = next((s for s in schemes if s["key"] == "pms"), None)
    if pms_row and pms_row["status"] != "confirmed":
        total_lo = 0  # not bankable until the fair is on the list
    eb = override.get("early_bird_deadline")
    eb_days = (_d(eb) - today).days if eb else None
    if ev.get("mode") != "exhibit":
        headline = "Visiting only: no stall rent to reimburse. Travel is not covered by any scheme." + (" A subsidised startup pod may be available (see below)." if "startup" in _applicable(ev) else "")
    elif pms_row and pms_row["status"] == "fair_not_listed":
        headline = f"PMS not claimable: this fair is not on the DC-MSME approved list (checked {pms_row['listing']['checked']}). Possible ₹0–{total_hi:,} only via another scheme or if the list changes; the 3-day follow-up re-checks."
    elif pms_row and pms_row["status"] == "check_list":
        headline = f"Possible money back ₹0–{total_hi:,}: PMS rules confirmed, but check that the fair is on the DC-MSME approved list (my.msme.gov.in → Trade Fairs Domestic) before counting on it."
    elif schemes:
        headline = f"Estimated money back: ₹{total_lo:,}–{total_hi:,} (best single scheme of {len(schemes)}; schemes do not stack on the same stall rent)."
    else:
        headline = "No scheme identified yet; the 3-day follow-up keeps checking."
    return {
        "headline": headline,
        "estimated_refund_inr": [total_lo, total_hi] if ev.get("mode") == "exhibit" else [0, 0],
        "schemes": schemes,
        "early_bird": {
            "deadline": eb, "days_left": eb_days, "note": override.get("early_bird_note") or "Organiser early-bird / space-booking deadline not published yet; the agent asks the organiser and re-checks every 3 days.",
            "status": "confirmed" if eb else "to_verify",
        },
        "status": override.get("status", "to_verify"),
        "last_checked": override.get("last_checked"),
        "next_check": (_d(override["last_checked"]) + timedelta(days=3)).isoformat() if override.get("last_checked") else today.isoformat(),
        "notes": override.get("notes", ""),
        "sources": override.get("sources", []),
    }


def deadlines(today: date | None = None, horizon_days: int = 120) -> list[dict[str, Any]]:
    """Every subsidy apply-by and early-bird date inside the horizon, soonest first."""
    today = today or date.today()
    out = []
    for ev in list_events():
        s = for_event(ev, today)
        for sc in s["schemes"]:
            if sc["apply_by"] and 0 <= (_d(sc["apply_by"]) - today).days <= horizon_days:
                out.append({"event_id": ev["id"], "event": ev["name"], "what": f"Apply: {sc['name']}", "date": sc["apply_by"], "days_left": (_d(sc["apply_by"]) - today).days, "link": sc["link"], "status": sc["status"]})
        eb = s["early_bird"]
        if eb["deadline"] and 0 <= (_d(eb["deadline"]) - today).days <= horizon_days:
            out.append({"event_id": ev["id"], "event": ev["name"], "what": "Organiser early-bird deadline", "date": eb["deadline"], "days_left": eb["days_left"], "link": ev.get("website", ""), "status": "confirmed"})
    return sorted(out, key=lambda x: x["date"])


def summary(today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    rows = []
    for ev in list_events():
        s = for_event(ev, today)
        rows.append({"event_id": ev["id"], "event": ev["name"], "mode": ev.get("mode"), "start": ev["start"], "headline": s["headline"],
                     "estimated_refund_inr": s["estimated_refund_inr"], "schemes": [x["key"] for x in s["schemes"]],
                     "early_bird_deadline": s["early_bird"]["deadline"], "status": s["status"], "last_checked": s["last_checked"]})
    return {"schemes": {k: {kk: vv for kk, vv in v.items() if kk != "sources"} for k, v in SCHEMES.items()}, "events": rows, "deadlines": deadlines(today)}

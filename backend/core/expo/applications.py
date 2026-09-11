"""Subsidy application desk.

For every exhibit show and every scheme that can pay money back, build the
application the agent can prepare in advance: which portal or association,
the apply-by date, every form field pre-filled from Souveno's profile plus
the event, the documents to attach, the company facts still missing, and the
e-mail that opens the channel where the application goes through an
organiser, association or export council.

Government portals (my.msme.gov.in, TS-iPASS) need Santosh's Udyam login and
a phone OTP, so the agent fills everything up to the Submit button; those two
taps stay with him. Passwords and OTPs are never stored.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from backend.core.expo import subsidy
from backend.core.expo.catalog import list_events
from backend.core.expo.planner import SOUVENO_PROFILE

# Facts the agent needs once. `secret: False` for all of them: these are
# registration numbers and a reimbursement account, not credentials.
COMPANY_FIELDS: list[dict[str, Any]] = [
    {"key": "udyam_number", "label": "Udyam Registration Number", "example": "UDYAM-TS-20-0012345", "for": ["pms", "telangana", "ic", "startup"], "group": "Registrations"},
    {"key": "msme_category", "label": "MSME category on the Udyam certificate", "example": "micro", "options": ["micro", "small", "medium"], "for": ["pms", "telangana", "ic"], "group": "Registrations"},
    {"key": "udyam_activity", "label": "Activity on Udyam (manufacturing / services) and NIC code", "example": "Services · NIC 62011 (software)", "for": ["pms"], "group": "Registrations"},
    {"key": "entity_type", "label": "Legal entity type", "example": "Proprietorship (the GSTIN's PAN starts with a P-type PAN)", "options": ["proprietorship", "partnership / LLP", "private limited", "OPC"], "for": ["pms", "telangana", "ic", "mai", "startup"], "group": "Registrations"},
    {"key": "pan", "label": "PAN of the enterprise / proprietor", "example": "BDNPP2011D", "for": ["pms", "telangana", "mai"], "group": "Registrations"},
    {"key": "incorporation_date", "label": "Date of commencement / incorporation", "example": "2025-08-01", "for": ["pms", "telangana", "startup"], "group": "Registrations"},
    {"key": "tsipass_ack", "label": "TS-iPASS / Telangana DIC acknowledgement number (if any)", "example": "TSIPASS/HYD/2025/xxxx", "for": ["telangana"], "group": "Registrations"},
    {"key": "dpiit_number", "label": "DPIIT Startup India recognition number (or 'not yet')", "example": "DIPP123456", "for": ["startup"], "group": "Registrations"},
    {"key": "social_category", "label": "Social category of the owner", "example": "General", "options": ["General", "SC", "ST", "OBC"], "for": ["pms"], "group": "Owner"},
    {"key": "owner_gender", "label": "Gender of the owner", "example": "Male", "options": ["Male", "Female"], "for": ["pms"], "group": "Owner"},
    {"key": "authorised_signatory", "label": "Authorised signatory (name, designation)", "example": "Santosh Padmaa, Proprietor", "for": ["pms", "telangana", "ic", "mai"], "group": "Owner"},
    {"key": "otp_mobile", "label": "Mobile linked to Udyam (receives the OTP at submit time)", "example": "+91 86393 32232", "for": ["pms", "telangana"], "group": "Owner"},
    {"key": "udyam_email", "label": "E-mail on the Udyam certificate", "example": "souveno30@gmail.com", "for": ["pms"], "group": "Owner"},
    {"key": "employees", "label": "Number of employees", "example": "6", "for": ["pms", "telangana", "ic"], "group": "Business"},
    {"key": "turnover_fy2526", "label": "Turnover FY 2025-26 (₹)", "example": "18,50,000", "for": ["pms", "telangana", "ic", "mai"], "group": "Business"},
    {"key": "export_turnover", "label": "Export turnover FY 2025-26 (₹, 0 if none)", "example": "0", "for": ["mai", "ic"], "group": "Business"},
    {"key": "memberships", "label": "Association memberships held (FTCCI, TiE, ESC, NASSCOM, AIPMA, IEEMA…)", "example": "none yet", "for": ["ic", "mai"], "group": "Business"},
    {"key": "bank_account_name", "label": "Reimbursement account — name on the account", "example": "Souveno AI Solutions", "for": ["pms", "telangana", "ic", "mai"], "group": "Bank (for reimbursement, current account)"},
    {"key": "bank_account_number", "label": "Reimbursement account number", "example": "5020XXXXXXXXXX", "for": ["pms", "telangana", "ic", "mai"], "group": "Bank (for reimbursement, current account)"},
    {"key": "bank_ifsc", "label": "IFSC", "example": "HDFC0001234", "for": ["pms", "telangana", "ic", "mai"], "group": "Bank (for reimbursement, current account)"},
    {"key": "bank_name_branch", "label": "Bank and branch", "example": "HDFC Bank, Ameerpet", "for": ["pms", "telangana", "ic", "mai"], "group": "Bank (for reimbursement, current account)"},
    {"key": "docs_folder", "label": "Google Drive folder link with scans: Udyam certificate, GST certificate, PAN, cancelled cheque, incorporation proof, product brochure, 2 photos of a previous stall if any", "example": "https://drive.google.com/drive/folders/…", "for": ["pms", "telangana", "ic", "mai", "startup"], "group": "Documents"},
]

DOCS: dict[str, list[str]] = {
    "pms": ["Udyam Registration Certificate", "GST registration certificate", "PAN", "Cancelled cheque of the reimbursement account", "Organiser's stall-space invoice (proforma before, tax invoice after)", "Proof of stall-rent payment (bank statement / UTR)", "Organiser's participation certificate (after the show)", "2–4 photographs of the stall with the Souveno fascia (after the show)", "Product brochure / catalogue"],
    "telangana": ["Udyam Registration Certificate", "TS-iPASS acknowledgement", "GST certificate", "Stall-rent invoice and payment proof", "Participation certificate", "Stall photographs", "Bank details (cancelled cheque)"],
    "ic": ["Udyam Registration Certificate", "Covering letter to the association joining its delegation", "Company profile and product brochure", "Passport copies of the travellers", "Estimated airfare and stall-rent quotes"],
    "mai": ["EPC membership certificate (12+ months)", "IEC (Import Export Code)", "Export turnover statement / CA certificate", "Stall booking confirmation in the India pavilion", "Airfare quotes (economy)"],
    "startup": ["DPIIT recognition certificate", "Udyam certificate", "Pitch deck / one-pager", "Founder ID"],
}

CHANNEL: dict[str, dict[str, str]] = {
    "pms": {"channel": "portal", "portal": "my.msme.gov.in → Procurement & Marketing Support → Trade Fairs Domestic", "link": "https://my.msme.gov.in/MyMsme/Reg/COM_Fair.aspx", "who_submits": "Santosh (Udyam login + OTP); the agent pre-fills everything"},
    "telangana": {"channel": "portal", "portal": "TS-iPASS / District Industries Centre, Hyderabad (marketing assistance claim)", "link": "https://ipass.telangana.gov.in/", "who_submits": "Santosh (TS-iPASS login); claim is filed after the show"},
    "ic": {"channel": "association", "portal": "MSME International Cooperation scheme — via a registered industry association's delegation (FTCCI Hyderabad / TiE / NSIC)", "link": "https://www.ic.msme.gov.in/", "who_submits": "The association applies in the ministry's call; Souveno joins as a delegation member"},
    "mai": {"channel": "epc", "portal": "Market Access Initiative — via ESC India (software export council)", "link": "https://www.escindia.in/", "who_submits": "ESC India files for its members; needs 12 months of membership first"},
    "startup": {"channel": "organiser", "portal": "Organiser's startup / DPIIT pod desk", "link": "", "who_submits": "Souveno applies to the organiser with the DPIIT certificate"},
}


def _d(s: str) -> date:
    return date.fromisoformat(s)


def company(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Souveno's profile plus whatever Santosh has filled into the intake form."""
    base = {
        "legal_name": SOUVENO_PROFILE["legal_name"], "brand": SOUVENO_PROFILE["company"], "gstin": SOUVENO_PROFILE["gstin"],
        "address": f"{SOUVENO_PROFILE['address']}, {SOUVENO_PROFILE['city']} {SOUVENO_PROFILE['pincode']}, {SOUVENO_PROFILE['state']}",
        "state": SOUVENO_PROFILE["state"], "district": "Hyderabad", "contact_name": SOUVENO_PROFILE["contact_name"], "designation": SOUVENO_PROFILE["designation"],
        "email": SOUVENO_PROFILE["email"], "phone": SOUVENO_PROFILE["phone"], "website": SOUVENO_PROFILE["website"],
        "products": SOUVENO_PROFILE["products"], "description": SOUVENO_PROFILE["description"], "founder_age": SOUVENO_PROFILE["founder_age"],
        "social_category": "General", "owner_gender": "Male", "authorised_signatory": f"{SOUVENO_PROFILE['contact_name']}, Proprietor",
        "otp_mobile": SOUVENO_PROFILE["phone"], "udyam_email": SOUVENO_PROFILE["email"], "bank_account_name": SOUVENO_PROFILE["legal_name"],
    }
    for k, v in (overrides or {}).items():
        if k in ("password", "otp", "pin", "portal_password"):
            continue  # never stored
        if v not in (None, ""):
            base[k] = v
    return base


def missing_for(scheme: str, comp: dict[str, Any]) -> list[dict[str, str]]:
    return [{"key": f["key"], "label": f["label"], "example": f["example"]} for f in COMPANY_FIELDS if scheme in f["for"] and not comp.get(f["key"])]


def _stall(ev: dict[str, Any]) -> tuple[int, int, int]:
    st = ev.get("stall") or {}
    sqm = int(st.get("suggested_sqm") or 9)
    rate = int(st.get("shell_rate_inr_sqm") or 10000)
    return sqm, rate, sqm * rate


def _email(ev: dict[str, Any], scheme: str, comp: dict[str, Any]) -> dict[str, str] | None:
    """The e-mail that opens the channel; sent from souveno30@gmail.com."""
    c = ev.get("exhibitor_contact") or {}
    org = ev.get("organiser") or c.get("org") or "the organiser"
    sqm, rate, rent = _stall(ev)
    sig = f"\n\nRegards,\n{comp['contact_name']}\n{comp['designation']}, {comp['legal_name']} (Souveno AI)\nGSTIN {comp['gstin']} · Hyderabad · {comp['phone']} · {comp['email']}\n{comp['website']}"
    if scheme in ("pms", "startup"):
        return {
            "to": c.get("email") or "",
            "subject": f"{ev['name']} — MSME / startup participation, stall rate card and PMS approval",
            "body": (f"Dear {org} team,\n\nSouveno AI Solutions (a Hyderabad-based AI startup and MSME) would like to exhibit at {ev['name']} "
                     f"({ev['start']} to {ev['end']}, {ev.get('venue', '')}, {ev.get('city', '')}) with a {sqm} sqm shell-scheme stall on a main aisle.\n\n"
                     "Could you please send us:\n"
                     "1. The exhibitor rate card and floor plan, with any early-bird / MSME / startup / first-time-exhibitor rates and their last dates.\n"
                     "2. Whether this edition is on the DC-MSME approved list for the MSME Procurement & Marketing Support (PMS) scheme, or has an MSME pavilion with subsidised stalls. If approval is pending, the expected date.\n"
                     "3. Any startup / DPIIT pod or pavilion, and how to apply for it.\n"
                     "4. The space-booking form and the proforma invoice format, so we can pay the advance from our current account and file the PMS application 30 days before the show.\n\n"
                     "We build a WhatsApp AI quote desk for manufacturers and distributors, and Vision AI for attendance, stock and vehicle counting; visitors to your show are exactly our customers." + sig),
        }
    if scheme == "ic":
        return {
            "to": "", "subject": f"MSME International Cooperation scheme — joining a delegation to {ev['name']}, {ev.get('city', '')}",
            "body": (f"Dear Sir / Madam,\n\nSouveno AI Solutions, a Hyderabad-based micro enterprise, plans to exhibit at {ev['name']} ({ev['start']} to {ev['end']}, {ev.get('city', '')}). "
                     "Under the Ministry of MSME International Cooperation (IC) scheme, airfare and stall rent are reimbursed to MSEs that travel as part of a registered association's delegation.\n\n"
                     "Are you organising or willing to sponsor a delegation to this show under the IC scheme? We would like to join it, or become a member so that we can. Please share the membership form, the delegation timeline and the documents you need from us." + sig),
        }
    if scheme == "mai":
        return {
            "to": "", "subject": "ESC India membership — Market Access Initiative support for foreign trade fairs",
            "body": ("Dear ESC India team,\n\nSouveno AI Solutions (Hyderabad; AI software: WhatsApp quote desk for manufacturers and distributors, Vision AI) is planning stalls at Gulf trade fairs in 2026-27 "
                     f"(first: {ev['name']}, {ev['start']}). We would like to become a member so that we qualify for Market Access Initiative support in India pavilions. Please send the membership form, fee, and the current list of MAI-approved fairs." + sig),
        }
    return None


def applications(today: date | None = None, company_overrides: dict[str, Any] | None = None, statuses: dict[str, Any] | None = None) -> dict[str, Any]:
    today = today or date.today()
    comp = company(company_overrides)
    statuses = statuses or {}
    rows: list[dict[str, Any]] = []
    for ev in list_events():
        if ev.get("mode") != "exhibit" or _d(ev["end"]) < today:
            continue
        info = subsidy.for_event(ev, today)
        sqm, rate, rent = _stall(ev)
        for s in info["schemes"]:
            key = s["key"]
            ch = CHANNEL.get(key, CHANNEL["pms"])
            app_id = f"{ev['id']}--{key}"
            saved = statuses.get(app_id) or {}
            status = saved.get("status") or "not_started"
            blocked = key == "pms" and s["status"] == "fair_not_listed"
            if blocked and status == "not_started":
                status = "blocked_not_listed"
            missing = missing_for(key, comp)
            apply_by = s.get("apply_by")
            window = "closed" if (apply_by and _d(apply_by) < today) else "open" if (apply_by and (_d(apply_by) - today).days <= 90) else "later" if apply_by else "after_show"
            prefilled = {
                "Name of the enterprise": comp["legal_name"], "Brand": comp["brand"], "Udyam Registration Number": comp.get("udyam_number", "{{udyam_number}}"),
                "MSME category": comp.get("msme_category", "{{msme_category}}"), "Type of enterprise": comp.get("entity_type", "{{entity_type}}"),
                "Activity": comp.get("udyam_activity", "Services — AI software"), "PAN": comp.get("pan", "{{pan}}"), "GSTIN": comp["gstin"],
                "Date of commencement": comp.get("incorporation_date", "{{incorporation_date}}"), "Address": comp["address"], "State / district": f"{comp['state']} / {comp['district']}",
                "Social category / gender of owner": f"{comp['social_category']} / {comp['owner_gender']}", "Authorised signatory": comp["authorised_signatory"],
                "Mobile (OTP)": comp["otp_mobile"], "E-mail": comp["udyam_email"], "Employees": comp.get("employees", "{{employees}}"), "Turnover FY 2025-26": comp.get("turnover_fy2526", "{{turnover_fy2526}}"),
                "Products / services to be exhibited": comp["products"],
                "Name of the fair": ev["name"], "Organiser": ev.get("organiser", ""), "Venue": f"{ev.get('venue', '')}, {ev.get('city', '')}", "Dates": f"{ev['start']} to {ev['end']}",
                "Stall size / type": f"{sqm} sqm shell scheme", "Stall rent (estimate, ex-GST)": f"₹{rent:,} (₹{rate:,}/sqm)", "Assistance sought": s.get("benefit", ""),
                "Bank for reimbursement": f"{comp.get('bank_account_name', '')} · A/c {comp.get('bank_account_number', '{{bank_account_number}}')} · IFSC {comp.get('bank_ifsc', '{{bank_ifsc}}')} · {comp.get('bank_name_branch', '{{bank_name_branch}}')}",
            }
            if key == "startup":
                prefilled["DPIIT recognition number"] = comp.get("dpiit_number", "{{dpiit_number}}")
            if key in ("ic", "mai"):
                prefilled["Travellers"] = "2 (economy, ex-Hyderabad)"
                prefilled["Export turnover FY 2025-26"] = comp.get("export_turnover", "{{export_turnover}}")
                prefilled["Association / EPC"] = comp.get("memberships", "{{memberships}}")
            if blocked:
                next_action = "Blocked: the fair is not on the DC-MSME approved list. Waiting on the organiser / the list update; the 3-day follow-up re-checks."
            elif missing:
                next_action = f"Need {len(missing)} company fact(s) from Santosh: " + ", ".join(m["label"].split(" (")[0] for m in missing[:4]) + ("…" if len(missing) > 4 else "")
            elif ch["channel"] == "portal" and key == "pms":
                next_action = f"Everything is pre-filled. Santosh logs in with Udyam + OTP and submits on the portal by {apply_by} (needs the organiser's proforma invoice first)."
            elif ch["channel"] == "portal":
                next_action = f"Claim after the show (by {s.get('claim_by')}) on TS-iPASS with the invoice, payment proof and participation certificate."
            elif ch["channel"] == "association":
                next_action = "Join a registered association's delegation (FTCCI / TiE / NSIC); the agent has drafted the request."
            elif ch["channel"] == "epc":
                next_action = "ESC India membership first (12 months before the claim); the agent has drafted the request."
            elif str(comp.get("dpiit_number", "")).lower() in ("", "not yet", "none", "no"):
                next_action = "Blocked: startup pods need DPIIT recognition, which is open only to a Pvt Ltd / LLP / registered partnership — Souveno is a proprietorship. Incorporate first, then apply for DPIIT (free, ~2 weeks)."
            else:
                next_action = "Apply to the organiser's startup pod desk with the DPIIT certificate."
            rows.append({
                "id": app_id, "event_id": ev["id"], "event_name": ev["name"], "event_start": ev["start"], "city": ev.get("city", ""),
                "scheme_key": key, "scheme_name": s["name"], "scheme_status": s["status"], "listing": s.get("listing"),
                "channel": ch["channel"], "portal": ch["portal"], "link": ch["link"] or s.get("link", ""), "who_submits": ch["who_submits"],
                "apply_by": apply_by, "claim_by": s.get("claim_by"), "days_to_apply": s.get("days_to_apply"), "window": window,
                "estimated_refund_inr": s.get("estimated_refund_inr"), "status": status, "saved": saved,
                "prefilled": prefilled, "documents": DOCS.get(key, []), "missing_info": missing, "next_action": next_action,
                "email": _email(ev, key, comp),
            })
    rows.sort(key=lambda r: (r["apply_by"] or "9999", r["event_start"]))
    need = {}
    for f in COMPANY_FIELDS:
        if not comp.get(f["key"]) and any(f["key"] == m["key"] for r in rows for m in r["missing_info"]):
            need[f["key"]] = f
    return {
        "today": today.isoformat(), "count": len(rows),
        "ready": sum(1 for r in rows if not r["missing_info"] and r["status"] not in ("blocked_not_listed",)),
        "blocked": sum(1 for r in rows if r["status"] == "blocked_not_listed"),
        "company": {k: v for k, v in comp.items()},
        "fields": COMPANY_FIELDS, "missing_company_fields": list(need.values()),
        "statuses": ["not_started", "info_needed", "ready", "submitted", "approved", "claimed", "paid", "rejected", "blocked_not_listed"],
        "items": rows,
    }

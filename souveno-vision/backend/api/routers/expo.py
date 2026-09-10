"""Expo Agent API — event intelligence, itinerary, calendar export, form
auto-fill, business-card exchange, lead funnel and the live dashboard feed."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.core.expo import approvals as approval_engine
from backend.core.expo import cards as card_engine
from backend.core.expo import floorplan
from backend.core.expo import planner, scoring
from backend.core.expo.catalog import get_event, list_events, meta
from backend.core.expo.playbook import DROP_REASONS, LEAD_STATUSES, playbook
from backend.db import crud, models
from backend.db.database import get_db
from config.settings import settings

router = APIRouter(prefix="/api/expo", tags=["expo"])

PROFILE_KEY = "expo_profile"
VALID_STATUSES = {s["key"] for s in LEAD_STATUSES}


# ---------------------------------------------------------------- schemas
class PlanUpdate(BaseModel):
    decision: Optional[str] = None
    stall_number: Optional[str] = None
    hall: Optional[str] = None
    stall_status: Optional[str] = None
    flight_status: Optional[str] = None
    hotel_status: Optional[str] = None
    registration_status: Optional[str] = None
    budget_approved_inr: Optional[int] = None
    team: Optional[str] = None
    notes: Optional[str] = None


class LeadIn(BaseModel):
    event_id: str
    name: str = ""
    company: str = ""
    designation: str = ""
    email: str = ""
    phone: str = ""
    website: str = ""
    gstin: str = ""
    address: str = ""
    industry: str = ""
    segment: str = ""
    source: str = "manual"
    status: str = "new"
    reason: str = ""
    quote_requests_per_day: int = 0
    whatsapp_primary: bool = True
    fit_score: int = Field(0, ge=0, le=50)
    next_action: str = ""
    next_action_date: Optional[datetime] = None
    notes: str = ""


class LeadUpdate(BaseModel):
    name: Optional[str] = None
    company: Optional[str] = None
    designation: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    gstin: Optional[str] = None
    address: Optional[str] = None
    industry: Optional[str] = None
    segment: Optional[str] = None
    status: Optional[str] = None
    reason: Optional[str] = None
    quote_requests_per_day: Optional[int] = None
    whatsapp_primary: Optional[bool] = None
    fit_score: Optional[int] = Field(None, ge=0, le=50)
    next_action: Optional[str] = None
    next_action_date: Optional[datetime] = None
    notes: Optional[str] = None


class InteractionIn(BaseModel):
    kind: str = "meeting"
    summary: str = ""
    outcome: str = ""
    happened_at: Optional[datetime] = None


class CollaborationIn(BaseModel):
    event_id: str
    partner: str = ""
    company: str = ""
    kind: str = "reseller"
    stage: str = "idea"
    value: str = ""
    notes: str = ""
    lead_id: Optional[int] = None


class CollaborationUpdate(BaseModel):
    partner: Optional[str] = None
    company: Optional[str] = None
    kind: Optional[str] = None
    stage: Optional[str] = None
    value: Optional[str] = None
    notes: Optional[str] = None


class ExchangeIn(BaseModel):
    """What a visitor submits after scanning Souveno's QR card."""
    event_id: str = "walk-in"
    name: str = ""
    company: str = ""
    designation: str = ""
    email: str = ""
    phone: str = ""
    website: str = ""
    quote_requests_per_day: int = 0
    message: str = ""


class CardTextIn(BaseModel):
    event_id: str
    text: str
    create_lead: bool = True


# ---------------------------------------------------------------- helpers
def _lead_dict(l: models.ExpoLead) -> dict[str, Any]:
    return {
        "id": l.id, "lead_uid": l.lead_uid, "event_id": l.event_id, "name": l.name, "company": l.company,
        "designation": l.designation, "email": l.email, "phone": l.phone, "website": l.website, "gstin": l.gstin,
        "address": l.address, "industry": l.industry, "segment": l.segment, "source": l.source, "status": l.status,
        "reason": l.reason, "quote_requests_per_day": l.quote_requests_per_day, "whatsapp_primary": l.whatsapp_primary,
        "fit_score": l.fit_score, "next_action": l.next_action,
        "next_action_date": l.next_action_date.isoformat() if l.next_action_date else None,
        "card_image_path": l.card_image_path, "notes": l.notes,
        "created_at": l.created_at.isoformat() if l.created_at else None,
        "updated_at": l.updated_at.isoformat() if l.updated_at else None,
        "interactions": [{"id": i.id, "kind": i.kind, "summary": i.summary, "outcome": i.outcome,
                          "happened_at": i.happened_at.isoformat() if i.happened_at else None} for i in l.interactions],
    }


def _plan_dict(p: models.ExpoEventPlan | None, event_id: str) -> dict[str, Any]:
    if not p:
        return {"event_id": event_id, "decision": "attend", "stall_number": "", "hall": "", "stall_status": "not_started",
                "flight_status": "not_started", "hotel_status": "not_started", "registration_status": "not_started",
                "budget_approved_inr": 0, "team": "Santosh, Mardan", "notes": ""}
    return {"event_id": p.event_id, "decision": p.decision, "stall_number": p.stall_number, "hall": p.hall,
            "stall_status": p.stall_status, "flight_status": p.flight_status, "hotel_status": p.hotel_status,
            "registration_status": p.registration_status, "budget_approved_inr": p.budget_approved_inr,
            "team": p.team, "notes": p.notes, "updated_at": p.updated_at.isoformat() if p.updated_at else None}


def _profile(db: Session) -> dict[str, str]:
    return planner.autofill_profile(crud.get_setting(db, PROFILE_KEY, {}) or {})


def _require_event(event_id: str) -> dict[str, Any]:
    ev = get_event(event_id)
    if not ev:
        raise HTTPException(404, f"Unknown event '{event_id}'")
    return ev


# ---------------------------------------------------------------- catalogue
@router.get("/events")
def events(db: Session = Depends(get_db)):
    summary = planner.catalog_summary()
    plans = {p.event_id: _plan_dict(p, p.event_id) for p in db.query(models.ExpoEventPlan).all()}
    lead_counts = dict(db.query(models.ExpoLead.event_id, func.count(models.ExpoLead.id)).group_by(models.ExpoLead.event_id).all())
    for ev in summary["events"]:
        ev["plan"] = plans.get(ev["id"], _plan_dict(None, ev["id"]))
        ev["lead_count"] = int(lead_counts.get(ev["id"], 0))
        ev["travel_plan"] = planner.travel_plan(ev)
    return summary


@router.get("/events/{event_id}")
def event_detail(event_id: str, db: Session = Depends(get_db)):
    ev = _require_event(event_id)
    plan = db.query(models.ExpoEventPlan).filter_by(event_id=event_id).first()
    return {
        **ev,
        "evaluation": scoring.evaluate(ev),
        "travel_plan": planner.travel_plan(ev),
        "registration_answers": planner.registration_answers(ev, _profile(db)),
        "plan": _plan_dict(plan, event_id),
    }


@router.get("/itinerary")
def itinerary():
    return {"days": planner.attend_all_itinerary(), "clashes": planner.clashes(list_events())}


@router.get("/calendar.ics")
def calendar_ics(travel: bool = True):
    return Response(planner.to_ics(include_travel=travel), media_type="text/calendar",
                    headers={"Content-Disposition": "attachment; filename=souveno-expo-2026-27.ics"})


@router.get("/playbook")
def get_playbook():
    return playbook()


# ---------------------------------------------------------------- plans
@router.get("/plans/{event_id}")
def get_plan(event_id: str, db: Session = Depends(get_db)):
    _require_event(event_id)
    return _plan_dict(db.query(models.ExpoEventPlan).filter_by(event_id=event_id).first(), event_id)


@router.put("/plans/{event_id}")
def update_plan(event_id: str, body: PlanUpdate, db: Session = Depends(get_db)):
    _require_event(event_id)
    plan = db.query(models.ExpoEventPlan).filter_by(event_id=event_id).first()
    if not plan:
        plan = models.ExpoEventPlan(event_id=event_id)
        db.add(plan)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(plan, k, v)
    db.commit()
    db.refresh(plan)
    return _plan_dict(plan, event_id)


# ---------------------------------------------------------------- profile / card / autofill
@router.get("/profile")
def get_profile(db: Session = Depends(get_db)):
    return _profile(db)


@router.put("/profile")
def put_profile(body: dict[str, str], db: Session = Depends(get_db)):
    current = crud.get_setting(db, PROFILE_KEY, {}) or {}
    current.update({k: v for k, v in body.items() if isinstance(v, str)})
    crud.set_setting(db, PROFILE_KEY, current)
    return _profile(db)


@router.get("/profile/vcard", response_class=PlainTextResponse)
def profile_vcard(db: Session = Depends(get_db)):
    return Response(card_engine.vcard(_profile(db)), media_type="text/vcard",
                    headers={"Content-Disposition": "attachment; filename=souveno.vcf"})


@router.get("/profile/autofill.js", response_class=PlainTextResponse)
def autofill_script(event_id: Optional[str] = None, db: Session = Depends(get_db)):
    """Bookmarklet body: fills any organiser registration form by matching
    input name/id/label/placeholder against the profile keys."""
    profile = _profile(db)
    answers = planner.registration_answers(_require_event(event_id), profile) if event_id else {}
    data = {**profile, **answers}
    aliases = {
        "company": ["company", "organisation", "organization", "firm", "exhibitor", "business name"],
        "contact_name": ["name", "contact", "person", "full name", "your name"],
        "email": ["email", "e-mail"], "phone": ["phone", "mobile", "contact no", "whatsapp", "tel"],
        "website": ["website", "url", "web"], "designation": ["designation", "title", "role", "position"],
        "city": ["city"], "state": ["state"], "country": ["country"], "gstin": ["gst", "gstin"],
        "address": ["address"], "description": ["profile", "about", "description"],
        "products": ["product", "display", "exhibit"], "industry": ["industry", "sector", "nature"],
        "stall_size_sqm": ["size", "sqm", "area"], "purpose_of_visit": ["purpose"],
    }
    js = """(function(){var D=%s;var A=%s;function norm(s){return (s||'').toLowerCase();}
function labelFor(el){var l='';if(el.id){var lb=document.querySelector('label[for="'+el.id+'"]');if(lb)l+=' '+lb.textContent;}
var p=el.closest('label');if(p)l+=' '+p.textContent;return norm(el.name+' '+el.id+' '+el.placeholder+' '+(el.getAttribute('aria-label')||'')+' '+l);}
var n=0;document.querySelectorAll('input:not([type=hidden]):not([type=submit]):not([type=checkbox]):not([type=radio]),textarea,select').forEach(function(el){var key=labelFor(el);
for(var k in A){if(A[k].some(function(a){return key.indexOf(a)>=0;})&&D[k]){if(el.tagName==='SELECT'){var o=[].slice.call(el.options).find(function(o){return norm(o.textContent).indexOf(norm(D[k]).slice(0,6))>=0;});if(o){el.value=o.value;n++;}}else if(!el.value){el.value=D[k];el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));n++;}break;}}});
alert('Souveno autofill: '+n+' fields filled. Review, then submit.');})();""" % (json.dumps(data), json.dumps(aliases))
    return Response(js, media_type="application/javascript")


# ---------------------------------------------------------------- cards
def _lead_from_card(db: Session, event_id: str, data: dict[str, Any], source: str) -> models.ExpoLead:
    lead = models.ExpoLead(
        event_id=event_id, name=data.get("name", ""), company=data.get("company", ""),
        designation=data.get("designation", ""), email=data.get("email", ""), phone=data.get("phone", ""),
        website=data.get("website", ""), gstin=data.get("gstin", ""), address=data.get("address", ""),
        industry=data.get("industry", ""), source=source, status="new",
    )
    db.add(lead)
    db.flush()
    db.add(models.ExpoCardScan(lead_id=lead.id, event_id=event_id, raw_text=data.get("raw_text", ""),
                               method=data.get("method", ""), confidence=float(data.get("confidence", 0) or 0),
                               image_path=data.get("image_path")))
    return lead


@router.post("/cards/scan")
async def scan_card(event_id: str = Form(...), create_lead: bool = Form(True), text: Optional[str] = Form(None),
                    image: Optional[UploadFile] = File(None), db: Session = Depends(get_db)):
    _require_event(event_id) if event_id != "walk-in" else None
    image_bytes = None
    media_type = "image/jpeg"
    image_path = None
    if image is not None:
        image_bytes = await image.read()
        media_type = image.content_type or media_type
        card_dir = settings.card_images_dir
        ext = ".png" if "png" in media_type else ".jpg"
        image_path = card_dir / f"{event_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}{ext}"
        image_path.write_bytes(image_bytes)
    data = card_engine.extract_card(image_bytes=image_bytes, media_type=media_type, text=text)
    data["image_path"] = str(image_path) if image_path else None
    result: dict[str, Any] = {"extracted": data}
    if create_lead and (data.get("name") or data.get("company") or data.get("phone") or data.get("email")):
        lead = _lead_from_card(db, event_id, data, source="scan")
        lead.card_image_path = data["image_path"]
        db.commit()
        db.refresh(lead)
        result["lead"] = _lead_dict(lead)
    return result


@router.post("/cards/parse")
def parse_card(body: CardTextIn, db: Session = Depends(get_db)):
    data = card_engine.parse_card_text(body.text)
    result: dict[str, Any] = {"extracted": data}
    if body.create_lead and (data.get("name") or data.get("company") or data.get("phone") or data.get("email")):
        lead = _lead_from_card(db, body.event_id, data, source="scan")
        db.commit()
        db.refresh(lead)
        result["lead"] = _lead_dict(lead)
    return result


@router.post("/exchange")
def exchange(body: ExchangeIn, db: Session = Depends(get_db)):
    """Visitor scanned Souveno's QR: store their card, hand back ours."""
    if not (body.name or body.company or body.phone or body.email):
        raise HTTPException(400, "Share at least a name, company, phone or email")
    lead = models.ExpoLead(event_id=body.event_id, name=body.name, company=body.company, designation=body.designation,
                           email=body.email, phone=body.phone, website=body.website, source="exchange", status="new",
                           quote_requests_per_day=body.quote_requests_per_day, notes=body.message)
    db.add(lead)
    db.commit()
    db.refresh(lead)
    profile = _profile(db)
    return {"ok": True, "lead_uid": lead.lead_uid, "souveno": profile, "vcard": card_engine.vcard(profile),
            "calendly": profile.get("calendly"), "whatsapp": "https://wa.me/" + profile.get("phone", "").replace(" ", "").replace("+", "")}


# ---------------------------------------------------------------- leads
@router.get("/leads")
def list_leads(event_id: Optional[str] = None, status: Optional[str] = None, q: Optional[str] = None,
               db: Session = Depends(get_db)):
    query = db.query(models.ExpoLead)
    if event_id:
        query = query.filter(models.ExpoLead.event_id == event_id)
    if status:
        query = query.filter(models.ExpoLead.status == status)
    if q:
        like = f"%{q}%"
        query = query.filter((models.ExpoLead.name.ilike(like)) | (models.ExpoLead.company.ilike(like)) | (models.ExpoLead.phone.ilike(like)))
    return [_lead_dict(l) for l in query.order_by(models.ExpoLead.created_at.desc()).all()]


@router.post("/leads", status_code=201)
def create_lead(body: LeadIn, db: Session = Depends(get_db)):
    if body.status not in VALID_STATUSES:
        raise HTTPException(400, f"status must be one of {sorted(VALID_STATUSES)}")
    lead = models.ExpoLead(**body.model_dump())
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return _lead_dict(lead)


@router.get("/leads/{lead_id}")
def get_lead(lead_id: int, db: Session = Depends(get_db)):
    lead = db.get(models.ExpoLead, lead_id)
    if not lead:
        raise HTTPException(404, "lead not found")
    return _lead_dict(lead)


@router.patch("/leads/{lead_id}")
def update_lead(lead_id: int, body: LeadUpdate, db: Session = Depends(get_db)):
    lead = db.get(models.ExpoLead, lead_id)
    if not lead:
        raise HTTPException(404, "lead not found")
    changes = body.model_dump(exclude_none=True)
    if "status" in changes and changes["status"] not in VALID_STATUSES:
        raise HTTPException(400, f"status must be one of {sorted(VALID_STATUSES)}")
    if changes.get("status") in ("not_converted", "left_midway") and not (changes.get("reason") or lead.reason):
        raise HTTPException(400, "a reason is required when marking not_converted or left_midway")
    for k, v in changes.items():
        setattr(lead, k, v)
    db.commit()
    db.refresh(lead)
    return _lead_dict(lead)


@router.delete("/leads/{lead_id}", status_code=204)
def delete_lead(lead_id: int, db: Session = Depends(get_db)):
    lead = db.get(models.ExpoLead, lead_id)
    if not lead:
        raise HTTPException(404, "lead not found")
    db.delete(lead)
    db.commit()
    return Response(status_code=204)


@router.post("/leads/{lead_id}/interactions", status_code=201)
def add_interaction(lead_id: int, body: InteractionIn, db: Session = Depends(get_db)):
    lead = db.get(models.ExpoLead, lead_id)
    if not lead:
        raise HTTPException(404, "lead not found")
    it = models.ExpoInteraction(lead_id=lead.id, event_id=lead.event_id, kind=body.kind, summary=body.summary,
                                outcome=body.outcome, happened_at=body.happened_at or datetime.utcnow())
    db.add(it)
    db.commit()
    db.refresh(lead)
    return _lead_dict(lead)


# ---------------------------------------------------------------- collaborations
def _collab_dict(c: models.ExpoCollaboration) -> dict[str, Any]:
    return {"id": c.id, "event_id": c.event_id, "lead_id": c.lead_id, "partner": c.partner, "company": c.company,
            "kind": c.kind, "stage": c.stage, "value": c.value, "notes": c.notes,
            "created_at": c.created_at.isoformat() if c.created_at else None}


@router.get("/collaborations")
def list_collaborations(event_id: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(models.ExpoCollaboration)
    if event_id:
        q = q.filter_by(event_id=event_id)
    return [_collab_dict(c) for c in q.order_by(models.ExpoCollaboration.created_at.desc()).all()]


@router.post("/collaborations", status_code=201)
def create_collaboration(body: CollaborationIn, db: Session = Depends(get_db)):
    c = models.ExpoCollaboration(**body.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return _collab_dict(c)


@router.patch("/collaborations/{collab_id}")
def update_collaboration(collab_id: int, body: CollaborationUpdate, db: Session = Depends(get_db)):
    c = db.get(models.ExpoCollaboration, collab_id)
    if not c:
        raise HTTPException(404, "collaboration not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(c, k, v)
    db.commit()
    db.refresh(c)
    return _collab_dict(c)


# ---------------------------------------------------------------- dashboard
@router.get("/dashboard")
def dashboard(event_id: Optional[str] = Query(None), db: Session = Depends(get_db)):
    q = db.query(models.ExpoLead)
    if event_id:
        q = q.filter(models.ExpoLead.event_id == event_id)
    leads = q.all()
    by_status = {s["key"]: 0 for s in LEAD_STATUSES}
    reasons: dict[str, int] = {}
    per_day: dict[str, int] = {}
    segments: dict[str, int] = {}
    sources: dict[str, int] = {}
    for l in leads:
        by_status[l.status] = by_status.get(l.status, 0) + 1
        if l.status in ("not_converted", "left_midway") and l.reason:
            reasons[l.reason] = reasons.get(l.reason, 0) + 1
        day = (l.created_at or datetime.utcnow()).date().isoformat()
        per_day[day] = per_day.get(day, 0) + 1
        if l.segment:
            segments[l.segment] = segments.get(l.segment, 0) + 1
        sources[l.source] = sources.get(l.source, 0) + 1
    met = len(leads)
    demos = sum(1 for l in leads if l.status in ("demo_booked", "pilot", "converted"))
    converted = by_status.get("converted", 0)
    pilots = by_status.get("pilot", 0)
    lost = by_status.get("not_converted", 0) + by_status.get("left_midway", 0)
    collabs = db.query(models.ExpoCollaboration)
    if event_id:
        collabs = collabs.filter_by(event_id=event_id)
    collabs = collabs.all()
    interactions = db.query(models.ExpoInteraction)
    if event_id:
        interactions = interactions.filter_by(event_id=event_id)
    developments = [{"lead_id": i.lead_id, "kind": i.kind, "summary": i.summary, "outcome": i.outcome,
                     "happened_at": i.happened_at.isoformat() if i.happened_at else None}
                    for i in interactions.order_by(models.ExpoInteraction.happened_at.desc()).limit(25).all()]
    expected = None
    if event_id and (ev := get_event(event_id)):
        expected = scoring.evaluate(ev)["funnel"]
    return {
        "event_id": event_id,
        "leads_generated": met,
        "clients_met": met,
        "qualified": by_status.get("qualified", 0) + demos,
        "demos": demos,
        "pilots": pilots,
        "converted": converted,
        "not_converted": by_status.get("not_converted", 0),
        "left_midway": by_status.get("left_midway", 0),
        "conversion_rate_pct": round(100 * converted / met, 1) if met else 0.0,
        "by_status": by_status,
        "reasons": sorted(({"reason": r, "count": n} for r, n in reasons.items()), key=lambda x: -x["count"]),
        "reason_catalog": DROP_REASONS,
        "leads_per_day": [{"date": d, "count": n} for d, n in sorted(per_day.items())],
        "segments": segments,
        "sources": sources,
        "collaborations": [_collab_dict(c) for c in collabs],
        "developments": developments,
        "expected": expected,
        "lost": lost,
    }


# ---------------------------------------------------------------- approvals (propose -> one tap -> execute)
class ApprovalDecision(BaseModel):
    decision: str  # approve | reject
    notes: str = ""
    execute: Optional[bool] = None  # default: settings.expo_auto_execute


class ApprovalEdit(BaseModel):
    amount_inr: Optional[int] = None
    payee: Optional[str] = None
    executor: Optional[str] = None
    details: Optional[dict[str, Any]] = None
    notes: Optional[str] = None


@router.get("/approvals")
def list_approvals(status: Optional[str] = None, event_id: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(models.ExpoApproval)
    if status:
        q = q.filter(models.ExpoApproval.status == status)
    if event_id:
        q = q.filter(models.ExpoApproval.event_id == event_id)
    rows = q.order_by(models.ExpoApproval.deadline.asc().nullslast(), models.ExpoApproval.proposed_at.desc()).all()
    items = [approval_engine.to_dict(r) for r in rows]
    for it in items:  # refresh the flight window against today's date
        if it["kind"] == "flight" and it["details"].get("depart"):
            it["details"]["booking_window"] = approval_engine.flight_booking_window(datetime.fromisoformat(it["details"]["depart"]).date(), international=bool(it["details"].get("international")))
    return {"rails": {"razorpayx": bool(settings.razorpayx_key_id), "duffel": bool(settings.duffel_access_token), "auto_execute": settings.expo_auto_execute},
            "policy": {"flights": "domestic: >= 30 days before, 60+ when possible; international: >= 45 days before, 90+ when possible; visas 21 days before"},
            "items": items}


@router.post("/approvals/propose", status_code=201)
def propose_approvals(event_id: Optional[str] = None, horizon_days: int = 90, db: Session = Depends(get_db)):
    if event_id:
        created = approval_engine.propose(db, _require_event(event_id))
    else:
        created = approval_engine.propose_all(db, horizon_days=horizon_days)
    return {"created": [approval_engine.to_dict(r) for r in created]}


@router.patch("/approvals/{approval_id}")
def edit_approval(approval_id: int, body: ApprovalEdit, db: Session = Depends(get_db)):
    row = db.get(models.ExpoApproval, approval_id)
    if not row:
        raise HTTPException(404, "approval not found")
    if row.status not in ("proposed",):
        raise HTTPException(400, "only proposed items can be edited")
    for k in ("amount_inr", "payee", "executor", "notes"):
        v = getattr(body, k)
        if v is not None:
            setattr(row, k, v)
    if body.details is not None:
        row.details_json = json.dumps({**json.loads(row.details_json or "{}"), **body.details})
    db.commit()
    db.refresh(row)
    return approval_engine.to_dict(row)


@router.post("/approvals/{approval_id}/decide")
def decide_approval(approval_id: int, body: ApprovalDecision, db: Session = Depends(get_db)):
    row = db.get(models.ExpoApproval, approval_id)
    if not row:
        raise HTTPException(404, "approval not found")
    if body.decision not in ("approve", "reject"):
        raise HTTPException(400, "decision must be approve or reject")
    if row.status not in ("proposed", "failed"):
        raise HTTPException(400, f"cannot decide an item in status {row.status}")
    row.status = "approved" if body.decision == "approve" else "rejected"
    row.decided_at = datetime.utcnow()
    if body.notes:
        row.notes = body.notes
    db.commit()
    run = settings.expo_auto_execute if body.execute is None else body.execute
    if row.status == "approved" and run:
        row = approval_engine.execute(db, row)
    db.refresh(row)
    return approval_engine.to_dict(row)


@router.post("/approvals/{approval_id}/execute")
def execute_approval(approval_id: int, db: Session = Depends(get_db)):
    row = db.get(models.ExpoApproval, approval_id)
    if not row:
        raise HTTPException(404, "approval not found")
    if row.status != "approved":
        raise HTTPException(400, "only approved items can be executed")
    return approval_engine.to_dict(approval_engine.execute(db, row))


@router.post("/approvals/{approval_id}/mark-done")
def mark_done(approval_id: int, note: str = "", db: Session = Depends(get_db)):
    """Human completed a manual step (paid the advance, booked the ticket)."""
    row = db.get(models.ExpoApproval, approval_id)
    if not row:
        raise HTTPException(404, "approval not found")
    row.status = "executed"
    row.executed_at = datetime.utcnow()
    row.execution_json = json.dumps({"ok": True, "mode": "manual", "note": note})
    plan = db.query(models.ExpoEventPlan).filter_by(event_id=row.event_id).first()
    if not plan:
        plan = models.ExpoEventPlan(event_id=row.event_id)
        db.add(plan)
    if row.kind in ("stall_advance", "stall_balance"):
        plan.stall_status = "booked"
    elif row.kind == "flight":
        plan.flight_status = "booked"
    elif row.kind == "hotel":
        plan.hotel_status = "booked"
    elif row.kind == "visa":
        plan.notes = (plan.notes + "\n" if plan.notes else "") + f"Visa done ({note})"
    db.commit()
    db.refresh(row)
    return approval_engine.to_dict(row)


# ---------------------------------------------------------------- stall layouts
class LayoutIn(BaseModel):
    name: str = "organiser floor plan"
    width: float
    height: float
    units: str = "px"
    entrances: list[list[float]] = []
    registration: Optional[list[float]] = None
    food_court: list[list[float]] = []
    washrooms: list[list[float]] = []
    anchors: list[dict[str, Any]] = []
    noisy: list[list[float]] = []
    pillars: list[list[float]] = []
    aisles: list[dict[str, Any]] = []
    stalls: list[dict[str, Any]]
    top: int = 5


@router.get("/floorplans/{event_id}.svg")
def modelled_floorplan_svg(event_id: str, top: int = 5):
    _require_event(event_id)
    r = floorplan.recommend(event_id, top=top)
    if not r:
        raise HTTPException(404, "no venue model for this event yet")
    return Response(r["svg"], media_type="image/svg+xml")


@router.get("/floorplans/{event_id}")
def modelled_floorplan(event_id: str, top: int = 5):
    _require_event(event_id)
    r = floorplan.recommend(event_id, top=top)
    if not r:
        raise HTTPException(404, "no venue model for this event yet")
    return r


@router.post("/floorplans/score")
def score_floorplan(body: LayoutIn):
    """Rank the stalls the user traced on the organiser's plan."""
    if not body.stalls:
        raise HTTPException(400, "trace at least one candidate stall")
    lay = floorplan.layout_from_dict(body.model_dump())
    ranked = floorplan.rank(lay)
    d = floorplan.layout_to_dict(lay, ranked, body.top)
    d["svg"] = floorplan.to_svg(lay, ranked, body.top)
    return d

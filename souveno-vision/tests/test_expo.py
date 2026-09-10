"""Expo Agent — scoring, planner, card parsing and the API (isolated app so
the CV dependencies are not required)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.api.routers import expo as expo_router
from backend.core.expo import cards, planner, scoring
from backend.core.expo.catalog import list_events
from backend.db.database import Base, get_db


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """Isolated FastAPI app on a throwaway SQLite file, so the tests never
    touch data/souveno_vision.db and never import the CV stack."""
    db_file = tmp_path_factory.mktemp("expo") / "expo_test.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(expo_router.router)
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    engine.dispose()


# ---------------------------------------------------------------- scoring
def test_stars_rounding_and_bounds():
    assert scoring.stars_from_total(95) == 5.0
    assert scoring.stars_from_total(100) == 5.0
    assert scoring.stars_from_total(85) == 4.5
    assert scoring.stars_from_total(77) == 4.0
    assert scoring.stars_from_total(45) == 2.5
    assert scoring.stars_from_total(0) == 1.0


def test_catalog_is_ranked_with_plastivision_and_elecrama_on_top():
    ranked = scoring.rank(list_events())
    top = {e["id"] for e in ranked[:2]}
    assert top == {"plastivision-2027", "elecrama-2027"}
    for e in ranked:
        assert 1.0 <= e["evaluation"]["stars"] <= 5.0
        assert e["evaluation"]["funnel"]["leads"][0] <= e["evaluation"]["funnel"]["leads"][1]
        assert 0 <= e["evaluation"]["funnel"]["client_probability_pct"] <= 100


def test_budget_zero_travel_for_home_city():
    home = next(e for e in list_events() if e["id"] == "papexpo-2026")
    b = scoring.budget(home)
    assert b["flights_inr"] == [0, 0] and b["hotel_nights"] == 0
    away = next(e for e in list_events() if e["id"] == "elecrama-2027")
    b2 = scoring.budget(away, travellers=2)
    assert b2["hotel_nights"] == scoring.event_days(away) + 1
    assert b2["stall_inr"] > 0 and b2["total_inr"][0] < b2["total_inr"][1]


# ---------------------------------------------------------------- planner
def test_itinerary_covers_every_event_at_least_once():
    events = list_events()
    days = planner.attend_all_itinerary(events)
    covered = {d["event_id"] for d in days}
    assert covered == {e["id"] for e in events}
    dates = [d["date"] for d in days]
    assert dates == sorted(dates) and len(dates) == len(set(dates))


def test_clashes_detected_for_january_cluster():
    pairs = {frozenset((c["a"], c["b"])) for c in planner.clashes(list_events())}
    assert frozenset(("plastivision-2027", "imtex-2027")) in pairs
    assert frozenset(("plastivision-2027", "acetech-hyderabad-2027")) in pairs


def test_ics_export_has_all_events_and_travel_legs():
    ics = planner.to_ics()
    assert ics.startswith("BEGIN:VCALENDAR")
    assert ics.count("BEGIN:VEVENT") > len(list_events())  # travel legs added
    assert "ELECRAMA 2027" in ics and "DTSTART;VALUE=DATE:20270220" in ics


def test_travel_links_are_well_formed():
    ev = next(e for e in list_events() if e["id"] == "engiexpo-pune-2026")
    tp = planner.travel_plan(ev)
    assert tp["needs_travel"] and tp["outbound"]["date"] == "2026-11-20"
    assert "HYD-PNQ-20/11/2026" in tp["outbound"]["links"]["makemytrip"]
    assert tp["hotel"]["nights"] == 3


# ---------------------------------------------------------------- cards
def test_card_parser_extracts_fields():
    text = ("Rajesh Kumar\nManaging Director\nSri Balaji Pipes & Fittings Pvt Ltd\n+91 98480 12345\n"
            "rajesh@balajipipes.com\nwww.balajipipes.com\nPlot 12, IDA Jeedimetla, Hyderabad 500055\nGSTIN 36AAACB1234F1Z5")
    d = cards.parse_card_text(text)
    assert d["name"] == "Rajesh Kumar"
    assert d["company"].startswith("Sri Balaji Pipes")
    assert d["designation"] == "Managing Director"
    assert d["email"] == "rajesh@balajipipes.com"
    assert d["phone"] == "+919848012345"
    assert d["gstin"] == "36AAACB1234F1Z5"
    assert d["website"] == "https://balajipipes.com"
    assert d["confidence"] == 1.0


def test_vcard_contains_profile():
    v = cards.vcard(planner.autofill_profile())
    assert "BEGIN:VCARD" in v and "Souveno AI" in v and "+91 86393 32232" in v


# ---------------------------------------------------------------- api
def test_events_endpoint(client):
    r = client.get("/api/expo/events")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == len(list_events())
    assert body["events"][0]["evaluation"]["stars"] == 5.0
    assert "itinerary" in body and "clashes" in body


def test_event_detail_and_registration_answers(client):
    r = client.get("/api/expo/events/elecrama-2027")
    assert r.status_code == 200
    d = r.json()
    assert d["registration_answers"]["participation_type"] == "Exhibitor"
    assert d["registration_answers"]["company_name"] == "Souveno AI"
    assert d["registration_answers"]["gstin"] == "36BDNPP2011D2ZV"
    assert d["registration_answers"]["address"].startswith("7-1-22/12")
    assert d["registration_answers"]["pincode"] == "500016"
    assert client.get("/api/expo/events/nope").status_code == 404


def test_plan_update_roundtrip(client):
    r = client.put("/api/expo/plans/elecrama-2027", json={"decision": "exhibit", "stall_number": "H9-01", "flight_status": "booked"})
    assert r.status_code == 200 and r.json()["stall_number"] == "H9-01"
    assert client.get("/api/expo/plans/elecrama-2027").json()["flight_status"] == "booked"


def test_calendar_ics_and_playbook(client):
    r = client.get("/api/expo/calendar.ics")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar")
    p = client.get("/api/expo/playbook").json()
    assert len(p["drop_reasons"]) >= 10 and len(p["qualification_scorecard"]) == 10


def test_card_parse_creates_lead_and_funnel_updates(client):
    r = client.post("/api/expo/cards/parse", json={"event_id": "engiexpo-pune-2026",
                                                    "text": "Priya Shah\nOwner\nShah Fasteners Industries\n9876543210\npriya@shahfasteners.in"})
    assert r.status_code == 200
    lead = r.json()["lead"]
    assert lead["source"] == "scan" and lead["phone"] == "+919876543210"
    lid = lead["id"]
    # status change to not_converted needs a reason
    assert client.patch(f"/api/expo/leads/{lid}", json={"status": "not_converted"}).status_code == 400
    r = client.patch(f"/api/expo/leads/{lid}", json={"status": "not_converted", "reason": "Wants free trial, not paid pilot", "fit_score": 22})
    assert r.status_code == 200
    r = client.post(f"/api/expo/leads/{lid}/interactions", json={"kind": "demo", "summary": "Voice-note demo", "outcome": "neutral"})
    assert r.status_code == 201 and len(r.json()["interactions"]) == 1
    dash = client.get("/api/expo/dashboard", params={"event_id": "engiexpo-pune-2026"}).json()
    assert dash["leads_generated"] >= 1 and dash["not_converted"] >= 1
    assert dash["reasons"][0]["reason"] == "Wants free trial, not paid pilot"
    assert dash["expected"]["mode"] == "exhibit"


def test_exchange_returns_souveno_card(client):
    r = client.post("/api/expo/exchange", json={"event_id": "walk-in", "name": "Amit", "company": "Amit Cables", "phone": "9000000000"})
    assert r.status_code == 200
    assert "BEGIN:VCARD" in r.json()["vcard"] and r.json()["whatsapp"].startswith("https://wa.me/")
    assert client.post("/api/expo/exchange", json={"event_id": "walk-in"}).status_code == 400


def test_collaboration_crud(client):
    r = client.post("/api/expo/collaborations", json={"event_id": "bts-2026", "partner": "Tally partner", "company": "ABC Solutions", "kind": "erp_consultant"})
    assert r.status_code == 201
    cid = r.json()["id"]
    assert client.patch(f"/api/expo/collaborations/{cid}", json={"stage": "discussed"}).json()["stage"] == "discussed"
    assert any(c["id"] == cid for c in client.get("/api/expo/collaborations", params={"event_id": "bts-2026"}).json())


def test_autofill_script_is_javascript(client):
    r = client.get("/api/expo/profile/autofill.js", params={"event_id": "fastener-fair-india-2027"})
    assert r.status_code == 200 and "Souveno autofill" in r.text and "Exhibitor" in r.text


# ---------------------------------------------------------------- approvals
def test_proposals_compute_advance_and_travel():
    from backend.core.expo import approvals
    ev = next(e for e in list_events() if e["id"] == "elecrama-2027")
    ps = approvals.proposals_for_event(ev)
    kinds = [p["kind"] for p in ps]
    assert kinds == ["stall_advance", "flight", "hotel"]  # domestic: no visa
    adv = ps[0]
    assert adv["details"]["sqm"] == 12 and adv["details"]["total_inr"] == round(12 * 13000 * 1.18)
    assert adv["amount_inr"] == round(adv["details"]["total_inr"] * 0.5)
    assert adv["executor"] == "manual"  # no RazorpayX keys configured
    home = next(e for e in list_events() if e["id"] == "acetech-hyderabad-2027")
    assert [p["kind"] for p in approvals.proposals_for_event(home)] == ["stall_advance"]


def test_approval_flow_propose_approve_execute_manual(client):
    r = client.post("/api/expo/approvals/propose", params={"event_id": "engiexpo-pune-2026"})
    assert r.status_code == 201
    items = r.json()["created"]
    assert {i["kind"] for i in items} == {"stall_advance", "flight", "hotel"}
    # idempotent
    assert client.post("/api/expo/approvals/propose", params={"event_id": "engiexpo-pune-2026"}).json()["created"] == []
    stall = next(i for i in items if i["kind"] == "stall_advance")
    # amount can be corrected once the rate card arrives
    r = client.patch(f"/api/expo/approvals/{stall['id']}", json={"amount_inr": 60000, "details": {"rate_status": "organiser rate card"}})
    assert r.json()["amount_inr"] == 60000
    # reject the hotel, approve the stall (manual rail -> instruction, stays approved)
    hotel = next(i for i in items if i["kind"] == "hotel")
    assert client.post(f"/api/expo/approvals/{hotel['id']}/decide", json={"decision": "reject"}).json()["status"] == "rejected"
    d = client.post(f"/api/expo/approvals/{stall['id']}/decide", json={"decision": "approve", "execute": True}).json()
    assert d["status"] == "approved" and d["execution"]["mode"] == "manual" and "₹60,000" in d["execution"]["instruction"]
    done = client.post(f"/api/expo/approvals/{stall['id']}/mark-done", params={"note": "NEFT done"}).json()
    assert done["status"] == "executed"
    assert client.get("/api/expo/plans/engiexpo-pune-2026").json()["stall_status"] == "booked"
    lst = client.get("/api/expo/approvals").json()
    assert lst["rails"] == {"razorpayx": False, "duffel": False, "auto_execute": False}
    assert any(i["status"] == "executed" for i in lst["items"])


# ---------------------------------------------------------------- stall layouts
def test_modelled_layout_ranks_main_aisle_corners_first():
    from backend.core.expo import floorplan
    r = floorplan.recommend("elecrama-2027")
    assert r["modelled"] and r["stall_count"] > 200
    best = r["top"][0]
    assert best["open_sides"] >= 2 and best["score"] >= 75
    assert any("main aisle" in p for p in best["pros"])
    worst = r["avoid"][0]
    assert worst["score"] < 20 and "back wall" in worst["cons"]
    assert r["svg"].startswith("<svg") and best["number"] in r["svg"]


def test_custom_traced_layout_scores_and_penalises(client):
    body = {"width": 100, "height": 60, "units": "m", "entrances": [[50, 0]], "registration": [50, 2],
            "food_court": [[92, 54]], "anchors": [{"name": "Polycab", "x": 60, "y": 15}], "noisy": [[20, 55]],
            "stalls": [{"number": "H9-01", "x": 52, "y": 6, "open_sides": 2, "on_main_aisle": True},
                       {"number": "H9-88", "x": 18, "y": 54, "open_sides": 1, "back_wall": True},
                       {"number": "H9-40", "x": 70, "y": 30, "open_sides": 1}]}
    r = client.post("/api/expo/floorplans/score", json=body)
    assert r.status_code == 200
    d = r.json()
    assert not d["modelled"]
    assert d["top"][0]["number"] == "H9-01" and d["top"][0]["score"] > d["top"][1]["score"]
    worst = d["ranked"][-1]
    assert worst["number"] == "H9-88" and "next to noisy machinery zone" in worst["cons"] and "back wall" in worst["cons"]
    assert client.get("/api/expo/floorplans/elecrama-2027.svg").headers["content-type"].startswith("image/svg")
    assert client.post("/api/expo/floorplans/score", json={"width": 10, "height": 10, "stalls": []}).status_code == 400


def test_flight_booking_window_policy():
    from datetime import date
    from backend.core.expo.approvals import flight_booking_window
    today = date(2026, 9, 10)
    w = flight_booking_window(date(2027, 2, 19), today)  # ELECRAMA outbound
    assert w["status"] == "ideal" and w["preferred_by"] == "2026-12-21" and w["latest_by"] == "2027-01-20"
    w = flight_booking_window(date(2026, 10, 22), today)  # Hardware Fair outbound, 42 days out
    assert w["status"] == "urgent"
    w = flight_booking_window(date(2026, 9, 30), today)  # 20 days out
    assert w["status"] == "late"
    ev = next(e for e in list_events() if e["id"] == "elecrama-2027")
    from backend.core.expo import approvals
    fp = next(p for p in approvals.proposals_for_event(ev) if p["kind"] == "flight")
    assert fp["details"]["booking_window"]["policy"].startswith("book >= 30 days")
    assert fp["deadline"] <= fp["details"]["booking_window"]["preferred_by"]


def test_international_policy_and_visa():
    from datetime import date
    from backend.core.expo import approvals
    w = approvals.flight_booking_window(date(2027, 5, 10), date(2026, 9, 10), international=True)
    assert w["international"] and w["preferred_by"] == "2027-02-09" and w["latest_by"] == "2027-03-26" and w["status"] == "ideal"
    w = approvals.flight_booking_window(date(2026, 11, 2), date(2026, 9, 10), international=True)  # 53 days: inside 90, above 45
    assert w["status"] == "urgent"
    ev = next(e for e in list_events() if e["id"] == "middle-east-energy-2027")
    ps = approvals.proposals_for_event(ev)
    assert [p["kind"] for p in ps] == ["stall_advance", "flight", "hotel", "visa"]
    visa = ps[-1]
    assert visa["amount_inr"] == 18000 and visa["details"]["country"] == "UAE" and visa["details"]["apply_by"] == "2027-04-19"
    assert ps[1]["details"]["international"] is True

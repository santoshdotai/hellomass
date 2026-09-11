import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db.database import Base
from backend.db import crud
from backend.core.events import EventEngine


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    from backend.db import models  # noqa: F401 register tables
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_session_and_zone_crud_roundtrip(db):
    session = crud.create_session(db, filename="cafe.mp4", file_path="/tmp/cafe.mp4", fps=25.0,
                                   width=1920, height=1080, duration_seconds=60.0, total_frames=1500,
                                   demo_mode=True)
    assert session.id is not None
    fetched = crud.get_session(db, session.id)
    assert fetched.filename == "cafe.mp4"

    zones = crud.save_zones(db, session.id, None, [
        {"name": "Queue", "zone_type": "QUEUE_ZONE", "shape_type": "polygon",
         "points": [[0, 0], [1, 0], [1, 1], [0, 1]], "color": "#f5a623"},
    ])
    assert len(zones) == 1
    fetched_zones = crud.get_zones_for_session(db, session.id)
    assert len(fetched_zones) == 1
    assert crud.zone_to_dict(fetched_zones[0])["zone_type"] == "QUEUE_ZONE"


def test_event_open_then_close_computes_duration(db):
    session = crud.create_session(db, filename="cafe.mp4", file_path="/tmp/cafe.mp4", fps=25.0,
                                   width=1920, height=1080, duration_seconds=60.0, total_frames=1500,
                                   demo_mode=True)
    engine = EventEngine(db, session.id, "CAM-DEMO-01")

    event = engine.open_event("idle:7:Prep", "POTENTIAL_IDLE_STAFF", "Prep", [7], start_time=10.0,
                               severity="warning", confidence=0.7, metadata={})
    assert event["status"] == "open"
    assert event["event_id"].startswith("EVT-")

    # opening again with the same key must not create a duplicate DB row
    duplicate = engine.open_event("idle:7:Prep", "POTENTIAL_IDLE_STAFF", "Prep", [7], start_time=10.0,
                                   severity="warning", confidence=0.7, metadata={})
    assert duplicate["event_id"] == event["event_id"]
    assert len(crud.list_events(db, session.id)) == 1

    closed = engine.close_event("idle:7:Prep", end_time=42.0)
    assert closed["status"] == "closed"
    assert closed["duration_seconds"] == 32.0

    stored = crud.list_events(db, session.id)[0]
    assert stored.status == "closed"
    assert stored.duration_seconds == 32.0


def test_instant_event_is_immediately_closed_with_zero_duration(db):
    session = crud.create_session(db, filename="cafe.mp4", file_path="/tmp/cafe.mp4", fps=25.0,
                                   width=1920, height=1080, duration_seconds=60.0, total_frames=1500,
                                   demo_mode=True)
    engine = EventEngine(db, session.id, "CAM-DEMO-01")
    event = engine.instant_event("ZONE_ENTER", "Queue", [1], timestamp=3.0)
    assert event["status"] == "closed"
    assert event["duration_seconds"] == 0.0


def test_warning_event_creates_alert_and_resolves_on_close(db):
    session = crud.create_session(db, filename="cafe.mp4", file_path="/tmp/cafe.mp4", fps=25.0,
                                   width=1920, height=1080, duration_seconds=60.0, total_frames=1500,
                                   demo_mode=True)
    engine = EventEngine(db, session.id, "CAM-DEMO-01")
    engine.open_event("queue_warning:Queue", "QUEUE_WARNING", "Queue", [], start_time=0.0,
                       severity="warning", confidence=1.0, metadata={})
    active = crud.list_active_alerts(db, session.id)
    assert len(active) == 1

    engine.close_event("queue_warning:Queue", end_time=20.0)
    active_after = crud.list_active_alerts(db, session.id)
    assert len(active_after) == 0

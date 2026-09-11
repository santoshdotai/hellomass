"""
SQLAlchemy models for SOUVENO VISION demo storage (Phase 16).

Every entity carries fields that map cleanly onto the Stage 5 multi-tenant
cloud schema (businesses/branches/edge_devices/cameras/...) — for the
local demo, `camera_id` defaults to a single logical demo camera and there
is no business_id/branch_id split, but the shapes are compatible.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from backend.db.database import Base


def gen_uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


class VideoSession(Base):
    __tablename__ = "video_sessions"

    id = Column(Integer, primary_key=True)
    session_uid = Column(String, unique=True, default=lambda: gen_uid("SESSION"))
    camera_id = Column(String, default="CAM-DEMO-01")
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    fps = Column(Float, default=0)
    width = Column(Integer, default=0)
    height = Column(Integer, default=0)
    duration_seconds = Column(Float, default=0)
    total_frames = Column(Integer, default=0)
    status = Column(String, default="uploaded")  # uploaded|ready|analyzing|completed|error
    demo_mode = Column(Boolean, default=True)
    zone_preset_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    zones = relationship("Zone", back_populates="session", cascade="all, delete-orphan")
    tracks = relationship("Track", back_populates="session", cascade="all, delete-orphan")
    events = relationship("Event", back_populates="session", cascade="all, delete-orphan")
    metrics = relationship("MetricSnapshot", back_populates="session", cascade="all, delete-orphan")


class Zone(Base):
    __tablename__ = "zones"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("video_sessions.id"), nullable=True)
    preset_name = Column(String, nullable=True, index=True)
    name = Column(String, nullable=False)
    zone_type = Column(String, nullable=False)  # COUNTER_ZONE, QUEUE_ZONE, ... TABLE
    shape_type = Column(String, default="polygon")  # polygon | line
    points_json = Column(Text, nullable=False)  # JSON list of [x,y] normalized 0..1
    color = Column(String, default="#3ba7ff")
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("VideoSession", back_populates="zones")


class Track(Base):
    __tablename__ = "tracks"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("video_sessions.id"))
    track_id = Column(Integer, nullable=False)
    class_name = Column(String, default="person")
    role = Column(String, default="UNKNOWN")  # STAFF | CUSTOMER | UNKNOWN
    first_seen_seconds = Column(Float, default=0)
    last_seen_seconds = Column(Float, default=0)
    total_dwell_seconds = Column(Float, default=0)

    session = relationship("VideoSession", back_populates="tracks")


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    event_uid = Column(String, unique=True, default=lambda: gen_uid("EVT"))
    session_id = Column(Integer, ForeignKey("video_sessions.id"))
    camera_id = Column(String, default="CAM-DEMO-01")
    event_type = Column(String, nullable=False, index=True)
    zone_id = Column(String, nullable=True)
    track_ids_json = Column(Text, default="[]")
    start_time_seconds = Column(Float, nullable=False)
    end_time_seconds = Column(Float, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    confidence = Column(Float, default=1.0)
    severity = Column(String, default="info")  # info | warning | critical
    status = Column(String, default="open")  # open | closed | resolved
    metadata_json = Column(Text, default="{}")
    clip_path = Column(String, nullable=True)
    screenshot_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("VideoSession", back_populates="events")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True)
    alert_uid = Column(String, unique=True, default=lambda: gen_uid("ALERT"))
    event_id = Column(Integer, ForeignKey("events.id"), nullable=True)
    session_id = Column(Integer, ForeignKey("video_sessions.id"))
    alert_type = Column(String, nullable=False)
    title = Column(String, nullable=False)
    message = Column(String, default="")
    severity = Column(String, default="warning")
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)


class MetricSnapshot(Base):
    __tablename__ = "metrics"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("video_sessions.id"))
    video_time_seconds = Column(Float, nullable=False)
    metrics_json = Column(Text, nullable=False)  # full metrics dict at this point in time
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("VideoSession", back_populates="metrics")


class DailySummary(Base):
    __tablename__ = "daily_summaries"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("video_sessions.id"))
    summary_date = Column(DateTime, default=datetime.utcnow)
    stats_json = Column(Text, default="{}")
    ai_summary_text = Column(Text, default="")
    generated_by = Column(String, default="rule_based")  # rule_based | llm


class Setting(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, nullable=False)
    value = Column(Text, default="")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------------------------------------------------- Expo Agent
class ExpoEventPlan(Base):
    """Per-event decisions Souveno makes on top of the researched catalogue."""
    __tablename__ = "expo_event_plans"

    id = Column(Integer, primary_key=True)
    event_id = Column(String, unique=True, nullable=False, index=True)
    decision = Column(String, default="attend")  # attend | exhibit | skip
    stall_number = Column(String, default="")
    hall = Column(String, default="")
    stall_status = Column(String, default="not_started")  # not_started | enquired | booked
    flight_status = Column(String, default="not_started")  # not_started | searching | booked
    hotel_status = Column(String, default="not_started")
    registration_status = Column(String, default="not_started")  # not_started | form_filled | confirmed
    budget_approved_inr = Column(Integer, default=0)
    team = Column(String, default="Santosh, Mardan")
    notes = Column(Text, default="")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ExpoLead(Base):
    __tablename__ = "expo_leads"

    id = Column(Integer, primary_key=True)
    lead_uid = Column(String, unique=True, default=lambda: gen_uid("LEAD"))
    event_id = Column(String, index=True, nullable=False)
    name = Column(String, default="")
    company = Column(String, default="")
    designation = Column(String, default="")
    email = Column(String, default="")
    phone = Column(String, default="")
    website = Column(String, default="")
    gstin = Column(String, default="")
    address = Column(String, default="")
    industry = Column(String, default="")
    segment = Column(String, default="")  # A B C D E P X
    source = Column(String, default="manual")  # scan | exchange | manual | import
    status = Column(String, default="new", index=True)
    # new | qualified | demo_booked | pilot | converted | not_converted | left_midway
    reason = Column(String, default="")  # why not converted / left midway
    quote_requests_per_day = Column(Integer, default=0)
    whatsapp_primary = Column(Boolean, default=True)
    fit_score = Column(Integer, default=0)  # 0-50 qualification scorecard
    next_action = Column(String, default="")
    next_action_date = Column(DateTime, nullable=True)
    card_image_path = Column(String, nullable=True)
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    interactions = relationship("ExpoInteraction", back_populates="lead", cascade="all, delete-orphan")


class ExpoInteraction(Base):
    __tablename__ = "expo_interactions"

    id = Column(Integer, primary_key=True)
    lead_id = Column(Integer, ForeignKey("expo_leads.id"), nullable=False)
    event_id = Column(String, index=True)
    kind = Column(String, default="meeting")  # meeting | demo | call | whatsapp | email | followup
    summary = Column(Text, default="")
    outcome = Column(String, default="")  # positive | neutral | negative
    happened_at = Column(DateTime, default=datetime.utcnow)

    lead = relationship("ExpoLead", back_populates="interactions")


class ExpoCollaboration(Base):
    __tablename__ = "expo_collaborations"

    id = Column(Integer, primary_key=True)
    event_id = Column(String, index=True)
    lead_id = Column(Integer, ForeignKey("expo_leads.id"), nullable=True)
    partner = Column(String, default="")
    company = Column(String, default="")
    kind = Column(String, default="reseller")
    # reseller | erp_consultant | bsp | association | integration | investor | co_marketing | other
    stage = Column(String, default="idea")  # idea | discussed | proposal_sent | agreed | dropped
    value = Column(String, default="")
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ExpoCardScan(Base):
    __tablename__ = "expo_card_scans"

    id = Column(Integer, primary_key=True)
    lead_id = Column(Integer, ForeignKey("expo_leads.id"), nullable=True)
    event_id = Column(String, index=True)
    image_path = Column(String, nullable=True)
    raw_text = Column(Text, default="")
    method = Column(String, default="regex")
    confidence = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)


class ExpoActuals(Base):
    """What really happened at a show, entered after coming back. Drives calibration of future estimates."""
    __tablename__ = "expo_actuals"

    id = Column(Integer, primary_key=True)
    event_id = Column(String, unique=True, nullable=False, index=True)
    mode = Column(String, default="")  # exhibit | visit as actually done
    actual_cost_inr = Column(Integer, default=0)
    footfall_visitors = Column(Integer, default=0)  # what you saw / organiser's closing figure
    leads = Column(Integer, default=0)
    qualified = Column(Integer, default=0)
    demos = Column(Integer, default=0)
    paid_pilots = Column(Integer, default=0)
    revenue_inr = Column(Integer, default=0)  # first-year value of the clients won
    subsidy_received_inr = Column(Integer, default=0)
    stall_number = Column(String, default="")
    best_segments = Column(String, default="")  # comma-separated ICP keys that actually converted
    notes = Column(Text, default="")
    recorded_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ExpoApproval(Base):
    """A booking the agent proposes; money moves only after a human taps Approve."""
    __tablename__ = "expo_approvals"

    id = Column(Integer, primary_key=True)
    approval_uid = Column(String, unique=True, default=lambda: gen_uid("APR"))
    event_id = Column(String, index=True, nullable=False)
    kind = Column(String, nullable=False)  # stall_advance | stall_balance | flight | hotel | registration
    title = Column(String, default="")
    amount_inr = Column(Integer, default=0)
    currency = Column(String, default="INR")
    payee = Column(String, default="")
    details_json = Column(Text, default="{}")  # route/dates/rate/sqm/links/bank details
    status = Column(String, default="proposed", index=True)  # proposed | approved | rejected | executed | failed
    executor = Column(String, default="manual")  # manual | razorpayx | duffel | email
    execution_json = Column(Text, default="{}")
    deadline = Column(DateTime, nullable=True)
    proposed_at = Column(DateTime, default=datetime.utcnow)
    decided_at = Column(DateTime, nullable=True)
    executed_at = Column(DateTime, nullable=True)
    notes = Column(Text, default="")

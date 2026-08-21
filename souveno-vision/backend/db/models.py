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

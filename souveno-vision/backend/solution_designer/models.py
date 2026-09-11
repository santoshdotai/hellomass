"""SQLAlchemy tables for the Solution Designer.

Relational shape mirrors the assessment flow: a client has sites; a site
has camera groups, cameras, one NVR, one server and one network record;
an assessment snapshots the inputs and stores the calculation,
recommendation and proposal outputs as JSON so every report is
reproducible from what was known at the time.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from backend.db.database import Base
from backend.db.models import gen_uid


class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True)
    client_uid = Column(String, unique=True, default=lambda: gen_uid("CLT"))
    company_name = Column(String, nullable=False, index=True)
    contact_name = Column(String, default="")
    contact_email = Column(String, default="")
    contact_phone = Column(String, default="")
    industry = Column(String, default="other")
    created_at = Column(DateTime, default=datetime.utcnow)

    sites = relationship("Site", back_populates="client", cascade="all, delete-orphan")


class Site(Base):
    __tablename__ = "sites"

    id = Column(Integer, primary_key=True)
    site_uid = Column(String, unique=True, default=lambda: gen_uid("SITE"))
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    name = Column(String, nullable=False)
    address = Column(String, default="")
    city = Column(String, default="")
    employees = Column(Integer, nullable=True)
    shifts = Column(Integer, nullable=True)
    existing_camera_count = Column(Integer, nullable=True)
    operating_hours = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    client = relationship("Client", back_populates="sites")
    camera_groups = relationship("CameraGroup", back_populates="site", cascade="all, delete-orphan")
    cameras = relationship("Camera", back_populates="site", cascade="all, delete-orphan")
    nvrs = relationship("NVR", back_populates="site", cascade="all, delete-orphan")
    servers = relationship("Server", back_populates="site", cascade="all, delete-orphan")
    networks = relationship("Network", back_populates="site", cascade="all, delete-orphan")
    assessments = relationship("Assessment", back_populates="site", cascade="all, delete-orphan")


class CameraGroup(Base):
    """A set of identical cameras entered as one row (count > 1)."""
    __tablename__ = "camera_groups"

    id = Column(Integer, primary_key=True)
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=False)
    ref = Column(String, default="")
    name = Column(String, nullable=False)
    count = Column(Integer, default=1)
    area = Column(String, default="")
    spec_json = Column(Text, default="{}")  # full CameraSpec as entered
    created_at = Column(DateTime, default=datetime.utcnow)

    site = relationship("Site", back_populates="camera_groups")
    cameras = relationship("Camera", back_populates="group")


class Camera(Base):
    """An individual camera (count == 1). Optional link to a group."""
    __tablename__ = "cameras"

    id = Column(Integer, primary_key=True)
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=False)
    group_id = Column(Integer, ForeignKey("camera_groups.id"), nullable=True)
    ref = Column(String, default="")
    name = Column(String, nullable=False)
    area = Column(String, default="")
    make_model = Column(String, default="")
    camera_type = Column(String, nullable=True)
    resolution = Column(String, nullable=True)
    fps = Column(Float, nullable=True)
    bitrate_mbps = Column(Float, nullable=True)
    codec = Column(String, nullable=True)
    rtsp_available = Column(Boolean, nullable=True)
    onvif_available = Column(Boolean, nullable=True)
    mainstream_available = Column(Boolean, nullable=True)
    substream_available = Column(Boolean, nullable=True)
    is_ptz = Column(Boolean, nullable=True)
    spec_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)

    site = relationship("Site", back_populates="cameras")
    group = relationship("CameraGroup", back_populates="cameras")


class NVR(Base):
    __tablename__ = "nvrs"

    id = Column(Integer, primary_key=True)
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=False)
    brand = Column(String, default="")
    model = Column(String, default="")
    firmware = Column(String, default="")
    channel_count = Column(Integer, nullable=True)
    rtsp_available = Column(Boolean, nullable=True)
    api_sdk_available = Column(Boolean, nullable=True)
    outbound_stream_limit = Column(Integer, nullable=True)
    is_dvr = Column(Boolean, nullable=True)
    notes = Column(Text, default="")

    site = relationship("Site", back_populates="nvrs")


class Server(Base):
    __tablename__ = "servers"

    id = Column(Integer, primary_key=True)
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=False)
    has_gpu = Column(Boolean, nullable=True)
    cpu_model = Column(String, default="")
    cpu_cores = Column(Integer, nullable=True)
    ram_gb = Column(Float, nullable=True)
    gpu_model = Column(String, default="")
    gpu_vram_gb = Column(Float, nullable=True)
    gpu_count = Column(Integer, nullable=True)
    nvidia_smi_output = Column(Text, default="")
    existing_gpu_utilization_pct = Column(Float, nullable=True)
    existing_cpu_utilization_pct = Column(Float, nullable=True)
    os = Column(String, default="")
    notes = Column(Text, default="")

    site = relationship("Site", back_populates="servers")


class Network(Base):
    __tablename__ = "networks"

    id = Column(Integer, primary_key=True)
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=False)
    link_speed_mbps = Column(Float, nullable=True)
    camera_vlan = Column(String, default="")
    internet_restricted = Column(Boolean, nullable=True)
    cloud_allowed = Column(Boolean, nullable=True)
    poe_switch_capacity_ok = Column(Boolean, nullable=True)
    notes = Column(Text, default="")

    site = relationship("Site", back_populates="networks")


class UseCase(Base):
    """Use cases requested for an assessment (one row per selected use case)."""
    __tablename__ = "use_cases"

    id = Column(Integer, primary_key=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=False)
    use_case_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    in_pilot = Column(Boolean, default=False)
    recommendation_json = Column(Text, default="{}")

    assessment = relationship("Assessment", back_populates="use_cases")


class Assessment(Base):
    __tablename__ = "assessments"

    id = Column(Integer, primary_key=True)
    assessment_uid = Column(String, unique=True, default=lambda: gen_uid("ASMT"))
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=False)
    status = Column(String, default="completed")
    input_json = Column(Text, default="{}")  # the validated AssessmentRequest
    summary_json = Column(Text, default="{}")  # suitability summary + headline numbers
    required_alert_latency_s = Column(Float, nullable=True)
    operating_schedule = Column(String, default="")
    privacy_requirements = Column(Text, default="")
    evidence_retention_days = Column(Integer, default=30)
    created_at = Column(DateTime, default=datetime.utcnow)

    site = relationship("Site", back_populates="assessments")
    use_cases = relationship("UseCase", back_populates="assessment", cascade="all, delete-orphan")
    calculations = relationship("Calculation", back_populates="assessment", cascade="all, delete-orphan")
    recommendations = relationship("Recommendation", back_populates="assessment", cascade="all, delete-orphan")
    proposals = relationship("Proposal", back_populates="assessment", cascade="all, delete-orphan")


class Calculation(Base):
    __tablename__ = "calculations"

    id = Column(Integer, primary_key=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=False)
    name = Column(String, nullable=False)
    value = Column(Float, nullable=True)
    unit = Column(String, default="")
    formula = Column(Text, default="")
    inputs_json = Column(Text, default="{}")
    assumptions_json = Column(Text, default="[]")
    warnings_json = Column(Text, default="[]")

    assessment = relationship("Assessment", back_populates="calculations")


class Recommendation(Base):
    """One row per output block: suitability, compute, architecture, pilot, risks, actions."""
    __tablename__ = "recommendations"

    id = Column(Integer, primary_key=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=False)
    kind = Column(String, nullable=False, index=True)
    payload_json = Column(Text, default="{}")
    generated_by = Column(String, default="rule_based")  # rule_based | llm
    created_at = Column(DateTime, default=datetime.utcnow)

    assessment = relationship("Assessment", back_populates="recommendations")


class Proposal(Base):
    __tablename__ = "proposals"

    id = Column(Integer, primary_key=True)
    proposal_uid = Column(String, unique=True, default=lambda: gen_uid("PROP"))
    assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=False)
    version = Column(Integer, default=1)
    status = Column(String, default="preliminary")  # preliminary | pilot_completed | final
    commercial_json = Column(Text, default="{}")
    pricing_config_json = Column(Text, default="{}")
    report_html = Column(Text, default="")
    narrative_generated_by = Column(String, default="rule_based")
    created_at = Column(DateTime, default=datetime.utcnow)

    assessment = relationship("Assessment", back_populates="proposals")

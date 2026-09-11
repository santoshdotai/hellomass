"""Pydantic input/output schemas for the Solution Designer.

Validation rules: unknown values are represented as None (never as a
default that looks like data). Enumerations are enforced; numeric ranges
are sanity-checked so a typo (e.g. 25000 FPS) is rejected at the door.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.solution_designer.catalog import CODECS, RESOLUTIONS, USE_CASES

CameraType = Literal["ip_fixed", "ip_ptz", "ip_fisheye", "analog_dvr", "usb", "unknown"]
ViewType = Literal["overhead", "oblique", "eye_level"]
Lighting = Literal["good", "variable", "low", "ir_night", "backlit"]
Occlusion = Literal["none", "partial", "heavy"]
MotionBlur = Literal["none", "some", "severe"]
Stability = Literal["stable", "occasional_drops", "frequent_drops"]
Industry = Literal["manufacturing", "warehouse_logistics", "retail", "hospitality", "healthcare", "education",
                   "office_it", "pharma", "construction", "other"]


class CameraSpec(BaseModel):
    """One camera, or a group of identical cameras when count > 1."""
    ref: Optional[str] = Field(None, description="Client's camera ID / group code")
    name: str = Field(..., min_length=1, max_length=120)
    count: int = Field(1, ge=1, le=5000)
    area: Optional[str] = Field(None, max_length=120)
    make_model: Optional[str] = Field(None, max_length=160)
    camera_type: Optional[CameraType] = None
    resolution: Optional[str] = None
    fps: Optional[float] = Field(None, gt=0, le=120)
    bitrate_mbps: Optional[float] = Field(None, gt=0, le=100)
    codec: Optional[str] = None
    rtsp_available: Optional[bool] = None
    onvif_available: Optional[bool] = None
    mainstream_available: Optional[bool] = None
    substream_available: Optional[bool] = None
    is_ptz: Optional[bool] = None
    view_type: Optional[ViewType] = None
    lighting: Optional[Lighting] = None
    occlusion: Optional[Occlusion] = None
    motion_blur: Optional[MotionBlur] = None
    stream_stability: Optional[Stability] = None
    subject_distance_m: Optional[float] = Field(None, gt=0, le=200)
    subject_height_px: Optional[int] = Field(None, gt=0, le=4320)
    use_cases: list[str] = Field(default_factory=list, description="Use-case ids requested on this camera")
    notes: Optional[str] = None

    @field_validator("resolution")
    @classmethod
    def _res(cls, v):
        if v is None or v == "":
            return None
        key = str(v).lower().strip()
        if key not in RESOLUTIONS:
            raise ValueError(f"resolution must be one of {sorted(RESOLUTIONS)}; got '{v}'")
        return key

    @field_validator("codec")
    @classmethod
    def _codec(cls, v):
        if v is None or v == "":
            return None
        key = str(v).lower().replace(".", "").replace("-", "").strip()
        if key not in CODECS:
            raise ValueError(f"codec must be one of {sorted(CODECS)}; got '{v}'")
        return key

    @field_validator("use_cases")
    @classmethod
    def _uc(cls, v):
        bad = [u for u in v if u not in USE_CASES]
        if bad:
            raise ValueError(f"unknown use case(s): {bad}")
        return v


class NVRSpec(BaseModel):
    brand: Optional[str] = None
    model: Optional[str] = None
    firmware: Optional[str] = None
    channel_count: Optional[int] = Field(None, ge=0, le=10000)
    rtsp_available: Optional[bool] = None
    api_sdk_available: Optional[bool] = None
    outbound_stream_limit: Optional[int] = Field(None, ge=0, le=10000)
    is_dvr: Optional[bool] = None
    notes: Optional[str] = None


class ServerSpec(BaseModel):
    has_gpu: Optional[bool] = None
    cpu_model: Optional[str] = None
    cpu_cores: Optional[int] = Field(None, ge=1, le=512)
    ram_gb: Optional[float] = Field(None, gt=0, le=4096)
    gpu_model: Optional[str] = None
    gpu_vram_gb: Optional[float] = Field(None, gt=0, le=512)
    gpu_count: Optional[int] = Field(None, ge=0, le=16)
    nvidia_smi_output: Optional[str] = None
    existing_gpu_utilization_pct: Optional[float] = Field(None, ge=0, le=100)
    existing_cpu_utilization_pct: Optional[float] = Field(None, ge=0, le=100)
    os: Optional[str] = None
    notes: Optional[str] = None


class NetworkSpec(BaseModel):
    link_speed_mbps: Optional[float] = Field(None, gt=0, le=100_000)
    camera_vlan: Optional[str] = None
    internet_restricted: Optional[bool] = None
    cloud_allowed: Optional[bool] = None
    poe_switch_capacity_ok: Optional[bool] = None
    notes: Optional[str] = None


class RequirementsSpec(BaseModel):
    use_cases: list[str] = Field(default_factory=list)
    required_alert_latency_s: Optional[float] = Field(None, gt=0, le=3600)
    operating_schedule: Optional[str] = None
    privacy_requirements: Optional[str] = None
    employee_identification_requested: bool = False
    evidence_retention_days: int = Field(30, ge=1, le=3650)
    events_per_camera_per_day: float = Field(20, ge=0, le=100000)
    average_clip_size_mb: float = Field(5, gt=0, le=1000)

    @field_validator("use_cases")
    @classmethod
    def _uc(cls, v):
        bad = [u for u in v if u not in USE_CASES]
        if bad:
            raise ValueError(f"unknown use case(s): {bad}")
        if not v:
            raise ValueError("at least one use case is required")
        return v


class CalculationSettings(BaseModel):
    network_safety_factor: float = Field(1.5, ge=1.0, le=5.0)
    analytics_fps: float = Field(5, gt=0, le=30)
    assumed_bitrate_mbps: Optional[float] = Field(None, gt=0, le=100,
                                                  description="Used only for cameras whose bitrate is unknown")
    model_size: Literal["nano", "small", "medium", "large"] = "small"


class ClientSpec(BaseModel):
    company_name: str = Field(..., min_length=1, max_length=200)
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    industry: Industry = "other"


class SiteSpec(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    address: Optional[str] = None
    city: Optional[str] = None
    employees: Optional[int] = Field(None, ge=0, le=1_000_000)
    shifts: Optional[int] = Field(None, ge=1, le=6)
    existing_camera_count: Optional[int] = Field(None, ge=0, le=100_000)
    operating_hours: Optional[str] = None


class AssessmentRequest(BaseModel):
    client: ClientSpec
    site: SiteSpec
    cameras: list[CameraSpec] = Field(default_factory=list)
    nvr: Optional[NVRSpec] = None
    server: Optional[ServerSpec] = None
    network: Optional[NetworkSpec] = None
    requirements: RequirementsSpec
    settings: CalculationSettings = Field(default_factory=CalculationSettings)
    pricing_overrides: Optional[dict] = None
    include_pilot_in_estimate: bool = True

    @model_validator(mode="after")
    def _counts(self):
        declared = self.site.existing_camera_count
        inventory = sum(c.count for c in self.cameras)
        if declared is not None and inventory > declared:
            raise ValueError(f"camera inventory ({inventory}) exceeds declared existing camera count ({declared})")
        if not self.cameras and not declared:
            raise ValueError("provide at least one camera/camera group or an existing camera count")
        return self


class PricingConfigIn(BaseModel):
    gst_rate: Optional[float] = Field(None, ge=0, lt=1)
    technical_pilot_fee: Optional[float] = Field(None, ge=0)
    pilot_max_cameras: Optional[int] = Field(None, ge=1)
    pilot_max_use_cases: Optional[int] = Field(None, ge=1)
    production_implementation_fee: Optional[float] = Field(None, ge=0)
    licence_tiers: Optional[list[dict]] = None
    pilot_credit_on_production: Optional[float] = Field(None, ge=0)
    hardware_note: Optional[str] = None
    exclusions: Optional[list[str]] = None

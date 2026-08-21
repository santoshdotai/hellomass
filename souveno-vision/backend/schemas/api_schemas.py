from typing import Optional

from pydantic import BaseModel, Field


class ZoneIn(BaseModel):
    name: str
    zone_type: str
    shape_type: str = "polygon"
    points: list[list[float]] = Field(..., description="Normalized [x,y] pairs, 0..1")
    color: str = "#3ba7ff"


class ZonesSaveRequest(BaseModel):
    session_id: Optional[int] = None
    preset_name: Optional[str] = None
    zones: list[ZoneIn]


class CostEstimateRequest(BaseModel):
    session_id: int
    staff_hourly_cost: float = 250.0
    average_order_value: float = 180.0
    estimated_monthly_spillage: float = 5000.0
    operating_hours_per_day: float = 12.0
    working_days_per_month: int = 26


class RuleUpdate(BaseModel):
    rule_name: str
    threshold_seconds: Optional[float] = None
    enabled: Optional[bool] = None


class RTSPTestRequest(BaseModel):
    camera_name: str
    rtsp_url: str
    username: str = ""
    password: str = ""


class RoleOverrideRequest(BaseModel):
    track_id: int
    role: str  # STAFF | CUSTOMER | UNKNOWN

"""Stage 3 — RTSP / NVR camera testing. Not required for the MP4 demo, but
fully wired so switching from file input to live cameras later is a
configuration step, not a rewrite."""
from __future__ import annotations

from fastapi import APIRouter

from backend.core.video_source import RTSPVideoSource
from backend.schemas.api_schemas import RTSPTestRequest

router = APIRouter(prefix="/api/cameras", tags=["cameras"])


@router.post("/test")
def test_camera(payload: RTSPTestRequest):
    result = RTSPVideoSource.test_connection(payload.rtsp_url, payload.username, payload.password)
    result["camera_name"] = payload.camera_name
    return result

"""Build a VideoSource from a plain specification dict (from YAML config, the
API or the demo screen).

    {"type": "webcam", "index": 0, "name": "Laptop Webcam"}
    {"type": "file", "path": "demo_assets/clip.mp4", "loop": true}
    {"type": "rtsp", "url": "rtsp://host/ch1", "username": "...", "password": "...", "stream_profile": "sub"}
    {"type": "synthetic"}

Connector types reserved for production integration are registered but not
implemented in this proof of concept: onvif (device discovery + media profile
to RTSP), nvr (NVR/VMS API such as Milestone, Hikvision HikCentral, Dahua DSS,
Genetec) and sdk (manufacturer SDK, e.g. HCNetSDK / NetSDK). They raise a
clear message so the UI can explain the integration path instead of failing."""
from __future__ import annotations

import os
from pathlib import Path

from src.sources.base import SourceError, VideoSource
from src.sources.rtsp import RTSPSource
from src.sources.synthetic import SyntheticSource
from src.sources.video_file import VideoFileSource
from src.sources.webcam import WebcamSource

FUTURE_CONNECTORS = {
    "onvif": "ONVIF discovery is a production connector: it finds cameras on the camera VLAN and resolves their "
             "media profiles to RTSP URLs. Not included in this proof of concept.",
    "nvr": "NVR/VMS API connectors (Milestone, HikCentral, Dahua DSS, Genetec, Uniview…) pull channel streams and "
           "recordings through the recorder instead of each camera. Not included in this proof of concept.",
    "sdk": "Manufacturer SDK connectors (e.g. Hikvision HCNetSDK, Dahua NetSDK) are used when a camera exposes "
           "neither RTSP nor ONVIF. Not included in this proof of concept.",
}


def _env(name: str | None) -> str:
    return os.environ.get(name, "") if name else ""


def create_source(spec: dict, base_dir: Path | None = None, rtsp_env: dict | None = None) -> VideoSource:
    kind = (spec.get("type") or "synthetic").lower()
    name = spec.get("name") or None
    if kind == "webcam":
        return WebcamSource(index=int(spec.get("index", spec.get("webcam_index", 0))), name=name or "Laptop Webcam",
                            width=int(spec.get("width", 0) or 0), height=int(spec.get("height", 0) or 0))
    if kind == "file":
        path = spec.get("path") or spec.get("video_path") or ""
        if not path:
            raise SourceError("Choose a video file first.")
        p = Path(path)
        if not p.is_absolute() and base_dir:
            p = base_dir / p
        return VideoFileSource(p, name=name, loop=bool(spec.get("loop", True)))
    if kind == "rtsp":
        rtsp_env = rtsp_env or {}
        profile = spec.get("stream_profile", "main")
        url = spec.get("url") or ""
        if not url:
            env_key = rtsp_env.get("substream_url_env") if profile == "sub" else rtsp_env.get("url_env")
            url = _env(env_key) or _env(rtsp_env.get("url_env"))
        username = spec.get("username") or _env(rtsp_env.get("username_env"))
        password = spec.get("password") or _env(rtsp_env.get("password_env"))
        if not url:
            raise SourceError("No RTSP URL provided. Enter one in the dashboard or set SOUVENO_RTSP_URL in .env.")
        return RTSPSource(url, name=name or "RTSP Camera", username=username or None, password=password or None,
                          transport=spec.get("transport", "tcp"), stream_profile=profile,
                          open_timeout_seconds=float(spec.get("open_timeout_seconds", 8)),
                          read_timeout_seconds=float(spec.get("read_timeout_seconds", 8)))
    if kind == "synthetic":
        return SyntheticSource(name=name or "Synthetic Factory Floor", fps=float(spec.get("fps", 15)),
                               realtime=bool(spec.get("realtime", True)))
    if kind in FUTURE_CONNECTORS:
        raise SourceError(FUTURE_CONNECTORS[kind])
    raise SourceError(f"Unknown source type '{kind}'. Use webcam, file, rtsp or synthetic.")


SOURCE_TYPES: dict[str, str] = {
    "webcam": "Laptop / USB webcam",
    "file": "Local video file (MP4/AVI/MOV)",
    "rtsp": "RTSP camera or NVR channel",
    "synthetic": "Synthetic demo scene (no camera needed)",
    "onvif": "ONVIF discovery (production connector, not in this build)",
    "nvr": "NVR / VMS API (production connector, not in this build)",
    "sdk": "Manufacturer SDK (production connector, not in this build)",
}

__all__ = ["create_source", "SOURCE_TYPES", "FUTURE_CONNECTORS", "SourceError", "VideoSource"]

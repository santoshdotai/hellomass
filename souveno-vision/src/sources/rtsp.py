"""RTSP camera / NVR channel connector.

* credentials are accepted at runtime (or from environment variables) and kept
  in memory only — `masked_url` is the only form that ever leaves this object;
* TCP transport by default (UDP drops frames on busy Wi-Fi/VLANs);
* open/read timeouts so a dead camera can never block the capture thread forever;
* reconnection with exponential backoff is driven by the FrameGrabber.

Not every camera speaks RTSP. Production integration may instead go through
ONVIF discovery, the NVR/VMS API, or a manufacturer SDK — those connectors plug
into the same VideoSource interface (see src/sources/factory.py)."""
from __future__ import annotations

import os
from typing import Optional

import cv2

from src.security.redaction import build_rtsp_url, mask_url
from src.sources.base import Frame, SourceError, SourceInfo, VideoSource
from src.sources.video_file import fourcc_to_str


class RTSPSource(VideoSource):
    kind = "rtsp"

    def __init__(self, url: str, name: str = "RTSP Camera", username: str | None = None,
                 password: str | None = None, transport: str = "tcp", stream_profile: str = "main",
                 open_timeout_seconds: float = 8.0, read_timeout_seconds: float = 8.0):
        super().__init__(name)
        if not url or not url.lower().startswith(("rtsp://", "rtsps://", "http://", "https://")):
            raise SourceError("Enter an RTSP URL that starts with rtsp://")
        self._full_url = build_rtsp_url(url, username, password)  # in memory only
        self._masked = mask_url(self._full_url)
        self.transport = transport if transport in ("tcp", "udp") else "tcp"
        self.stream_profile = stream_profile
        self.open_timeout_ms = int(open_timeout_seconds * 1000)
        self.read_timeout_ms = int(read_timeout_seconds * 1000)
        self._cap: Optional[cv2.VideoCapture] = None

    @property
    def masked_url(self) -> str:
        return self._masked

    def __repr__(self) -> str:  # never leak the full URL through repr/str
        return f"RTSPSource(name={self.name!r}, url={self._masked!r})"

    __str__ = __repr__

    def _set_ffmpeg_options(self) -> None:
        opts = f"rtsp_transport;{self.transport}"
        existing = os.environ.get("OPENCV_FFMPEG_CAPTURE_OPTIONS", "")
        if "rtsp_transport" not in existing:
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = f"{existing}|{opts}".strip("|") if existing else opts

    def open(self) -> SourceInfo:
        self._set_ffmpeg_options()
        params = []
        if hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
            params += [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, self.open_timeout_ms]
        if hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
            params += [cv2.CAP_PROP_READ_TIMEOUT_MSEC, self.read_timeout_ms]
        try:
            self._cap = cv2.VideoCapture(self._full_url, cv2.CAP_FFMPEG, params) if params else \
                cv2.VideoCapture(self._full_url, cv2.CAP_FFMPEG)
        except Exception as exc:
            raise SourceError(f"Could not start the RTSP client for {self._masked}: {type(exc).__name__}") from exc
        if not self._cap or not self._cap.isOpened():
            self._cap = None
            raise SourceError(
                f"Camera not reachable at {self._masked}. Check the IP/port, the stream path, the credentials, "
                f"that the camera VLAN is routable from this PC, and that Windows Firewall allows outbound RTSP (554).")
        try:
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # smallest internal buffer = lowest latency
        except Exception:
            pass
        ok, image = self._cap.read()
        if not ok or image is None:
            self._cap.release()
            self._cap = None
            raise SourceError(
                f"Connected to {self._masked} but no video frame arrived. Usually wrong credentials, wrong "
                f"channel/stream path, or a codec (H.265) this build cannot decode — try the substream.")
        fps = self._cap.get(cv2.CAP_PROP_FPS)
        self.info = SourceInfo(name=self.name, kind=self.kind, masked_url=self._masked,
                               width=int(image.shape[1]), height=int(image.shape[0]),
                               fps=float(fps) if fps and 1 <= fps <= 120 else 0.0, is_live=True,
                               codec=fourcc_to_str(self._cap.get(cv2.CAP_PROP_FOURCC)),
                               stream_profile=self.stream_profile,
                               extra={"transport": self.transport})
        self._opened = True
        return self.info

    def read(self) -> Optional[Frame]:
        if not self._cap:
            return None
        ok, image = self._cap.read()
        if not ok or image is None:
            return None
        return self._make_frame(image)

    def close(self) -> None:
        if self._cap:
            try:
                self._cap.release()
            except Exception:
                pass
        self._cap = None
        self._opened = False

    def describe(self) -> dict:
        d = super().describe()
        d["stream_profile"] = self.stream_profile
        d["transport"] = self.transport
        return d

"""
VideoSource abstraction (Stage 2 — the reason the rest of the pipeline never
needs to know whether frames came from an MP4 file, a live RTSP camera, an
NVR channel, or a webcam).

V0.1 ships FileVideoSource fully working. RTSPVideoSource, NVRVideoSource
and WebcamVideoSource are real, runnable implementations (OpenCV can open
rtsp:// URLs and webcam indices today) but are exercised through the
"Test Camera" flow (Stage 3), not the MP4 demo path — nothing about the
pipeline changes when you switch sources.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterator, Optional

import cv2
import numpy as np
from loguru import logger


@dataclass
class VideoInfo:
    fps: float
    width: int
    height: int
    total_frames: int  # 0 for endless live streams
    duration_seconds: float  # 0 for endless live streams
    source_type: str


class VideoSource(ABC):
    """Common interface every video input must implement."""

    source_type: str = "base"

    @abstractmethod
    def open(self) -> VideoInfo:
        ...

    @abstractmethod
    def frames(self) -> Iterator[tuple[int, float, np.ndarray]]:
        """Yields (frame_index, timestamp_seconds, frame_bgr)."""
        ...

    @abstractmethod
    def seek_seconds(self, seconds: float) -> None:
        ...

    @abstractmethod
    def release(self) -> None:
        ...

    @property
    @abstractmethod
    def is_live(self) -> bool:
        ...


class FileVideoSource(VideoSource):
    """Reads a pre-recorded MP4/MOV/AVI/MKV file (Phase 3)."""

    source_type = "file"

    def __init__(self, file_path: str):
        self.file_path = file_path
        self._cap: Optional[cv2.VideoCapture] = None
        self.info: Optional[VideoInfo] = None

    def open(self) -> VideoInfo:
        self._cap = cv2.VideoCapture(self.file_path)
        if not self._cap.isOpened():
            raise RuntimeError(f"Could not open video file: {self.file_path}")
        fps = self._cap.get(cv2.CAP_PROP_FPS) or 25.0
        width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps else 0
        self.info = VideoInfo(fps=fps, width=width, height=height, total_frames=total_frames,
                               duration_seconds=duration, source_type=self.source_type)
        logger.info(f"Opened video file {self.file_path}: {width}x{height} @ {fps:.1f}fps, {duration:.1f}s")
        return self.info

    def frames(self) -> Iterator[tuple[int, float, np.ndarray]]:
        assert self._cap is not None, "call open() first"
        idx = 0
        fps = self.info.fps if self.info else 25.0
        while True:
            ok, frame = self._cap.read()
            if not ok:
                break
            timestamp = idx / fps if fps else 0
            yield idx, timestamp, frame
            idx += 1

    def seek_seconds(self, seconds: float) -> None:
        if self._cap and self.info:
            frame_no = int(seconds * self.info.fps)
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, frame_no))

    def release(self) -> None:
        if self._cap:
            self._cap.release()
            self._cap = None

    @property
    def is_live(self) -> bool:
        return False


class RTSPVideoSource(VideoSource):
    """Live RTSP camera / NVR channel input (Stage 3).

    Handles reconnects and timeouts so the rest of the pipeline can treat
    a flaky camera link the same way it treats a finite file — it just
    keeps calling frames().
    """

    source_type = "rtsp"

    def __init__(self, rtsp_url: str, username: str = "", password: str = "",
                 reconnect_attempts: int = 5, reconnect_delay_seconds: float = 2.0):
        self.rtsp_url = self._inject_credentials(rtsp_url, username, password)
        self.reconnect_attempts = reconnect_attempts
        self.reconnect_delay_seconds = reconnect_delay_seconds
        self._cap: Optional[cv2.VideoCapture] = None
        self.info: Optional[VideoInfo] = None

    @staticmethod
    def _inject_credentials(url: str, username: str, password: str) -> str:
        if username and password and "@" not in url and "://" in url:
            scheme, rest = url.split("://", 1)
            return f"{scheme}://{username}:{password}@{rest}"
        return url

    def _safe_url_for_logging(self) -> str:
        # Never log credentials in plaintext.
        if "@" in self.rtsp_url:
            scheme, rest = self.rtsp_url.split("://", 1)
            return f"{scheme}://***:***@{rest.split('@', 1)[1]}"
        return self.rtsp_url

    def open(self) -> VideoInfo:
        self._cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
        if not self._cap.isOpened():
            raise RuntimeError(f"Could not connect to RTSP stream: {self._safe_url_for_logging()}")
        fps = self._cap.get(cv2.CAP_PROP_FPS) or 25.0
        width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.info = VideoInfo(fps=fps, width=width, height=height, total_frames=0,
                               duration_seconds=0, source_type=self.source_type)
        logger.info(f"Connected to RTSP stream {self._safe_url_for_logging()}: {width}x{height} @ {fps:.1f}fps")
        return self.info

    def frames(self) -> Iterator[tuple[int, float, np.ndarray]]:
        assert self._cap is not None, "call open() first"
        idx = 0
        attempts = 0
        start = time.time()
        while True:
            ok, frame = self._cap.read()
            if not ok:
                attempts += 1
                logger.warning(f"RTSP frame read failed (attempt {attempts}/{self.reconnect_attempts})")
                if attempts > self.reconnect_attempts:
                    logger.error("RTSP stream unrecoverable, stopping")
                    break
                time.sleep(self.reconnect_delay_seconds)
                self._reconnect()
                continue
            attempts = 0
            yield idx, time.time() - start, frame
            idx += 1

    def _reconnect(self):
        if self._cap:
            self._cap.release()
        self._cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)

    def seek_seconds(self, seconds: float) -> None:
        raise NotImplementedError("Cannot seek a live RTSP stream")

    def release(self) -> None:
        if self._cap:
            self._cap.release()
            self._cap = None

    @property
    def is_live(self) -> bool:
        return True

    @staticmethod
    def test_connection(rtsp_url: str, username: str = "", password: str = "", timeout_seconds: float = 5.0) -> dict:
        """Used by the 'TEST CAMERA' UI action. Returns connection diagnostics
        without ever including credentials in the response."""
        url = RTSPVideoSource._inject_credentials(rtsp_url, username, password)
        start = time.time()
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        connected = cap.isOpened()
        result = {"connected": False, "resolution": None, "fps": None, "latency_ms": None, "error": None}
        if connected:
            ok, _frame = cap.read()
            latency_ms = round((time.time() - start) * 1000, 1)
            if ok:
                result.update({
                    "connected": True,
                    "resolution": f"{int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))} x {int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}",
                    "fps": round(cap.get(cv2.CAP_PROP_FPS) or 0, 1),
                    "latency_ms": latency_ms,
                })
            else:
                result["error"] = "Connected but failed to read a frame (check credentials/stream path)"
        else:
            result["error"] = "Could not open stream (check URL, network reachability, credentials)"
        cap.release()
        return result


class NVRVideoSource(RTSPVideoSource):
    """An NVR channel is, from OpenCV's perspective, just another RTSP URL
    (NVRs expose per-channel RTSP endpoints). Subclassed separately so the
    Stage 3 ONVIF/NVR-discovery module has a clear extension point without
    touching RTSPVideoSource."""

    source_type = "nvr"


class WebcamVideoSource(VideoSource):
    """Local webcam input — useful for quick live testing of the pipeline
    without any camera infrastructure."""

    source_type = "webcam"

    def __init__(self, device_index: int = 0):
        self.device_index = device_index
        self._cap: Optional[cv2.VideoCapture] = None
        self.info: Optional[VideoInfo] = None

    def open(self) -> VideoInfo:
        self._cap = cv2.VideoCapture(self.device_index)
        if not self._cap.isOpened():
            raise RuntimeError(f"Could not open webcam index {self.device_index}")
        fps = self._cap.get(cv2.CAP_PROP_FPS) or 25.0
        width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.info = VideoInfo(fps=fps, width=width, height=height, total_frames=0,
                               duration_seconds=0, source_type=self.source_type)
        return self.info

    def frames(self) -> Iterator[tuple[int, float, np.ndarray]]:
        assert self._cap is not None
        idx = 0
        start = time.time()
        while True:
            ok, frame = self._cap.read()
            if not ok:
                break
            yield idx, time.time() - start, frame
            idx += 1

    def seek_seconds(self, seconds: float) -> None:
        raise NotImplementedError("Cannot seek a live webcam stream")

    def release(self) -> None:
        if self._cap:
            self._cap.release()
            self._cap = None

    @property
    def is_live(self) -> bool:
        return True

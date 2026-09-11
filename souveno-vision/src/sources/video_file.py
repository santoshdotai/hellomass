"""Local video file connector (MP4 / AVI / MOV / MKV) with optional replay loop."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import cv2

from src.sources.base import Frame, SourceError, SourceInfo, VideoSource

SUPPORTED_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".m4v", ".wmv", ".mpg", ".mpeg"}


def fourcc_to_str(value: float) -> str:
    try:
        v = int(value)
        s = "".join(chr((v >> (8 * i)) & 0xFF) for i in range(4))
        return s.strip("\x00 ") or ""
    except Exception:
        return ""


class VideoFileSource(VideoSource):
    kind = "file"

    def __init__(self, path: str | Path, name: str | None = None, loop: bool = True):
        path = Path(path)
        super().__init__(name or path.stem)
        self.path = path
        self.loop = loop
        self.loops_completed = 0
        self._cap: Optional[cv2.VideoCapture] = None
        self._fps = 25.0
        self._pos = 0

    @property
    def is_live(self) -> bool:
        return self.loop  # a looping file behaves like an endless stream

    @property
    def pace_to_fps(self) -> bool:
        return True

    def open(self) -> SourceInfo:
        if not self.path.exists():
            raise SourceError(f"Video file not found: {self.path.name}")
        if self.path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise SourceError(f"Unsupported video format '{self.path.suffix}'. Use MP4, AVI, MOV or MKV.")
        self._cap = cv2.VideoCapture(str(self.path))
        if not self._cap.isOpened():
            self._cap = None
            raise SourceError(
                f"Could not decode '{self.path.name}'. The codec may be missing — re-encode to H.264 MP4 "
                f"(for example with HandBrake or VLC) and try again.")
        fps = self._cap.get(cv2.CAP_PROP_FPS)
        self._fps = float(fps) if fps and 1.0 <= fps <= 240 else 25.0
        width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        codec = fourcc_to_str(self._cap.get(cv2.CAP_PROP_FOURCC))
        if width <= 0 or height <= 0:
            self._cap.release()
            self._cap = None
            raise SourceError(f"'{self.path.name}' has no readable video frames.")
        self._pos = 0
        self.info = SourceInfo(name=self.name, kind=self.kind, masked_url=f"file://{self.path.name}",
                               width=width, height=height, fps=self._fps, total_frames=total,
                               duration_seconds=(total / self._fps) if total else 0.0,
                               is_live=self.loop, codec=codec, extra={"loop": self.loop})
        self._opened = True
        return self.info

    def read(self) -> Optional[Frame]:
        if not self._cap:
            return None
        ok, image = self._cap.read()
        if not ok or image is None:
            if not self.loop:
                return None
            self.loops_completed += 1
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            self._pos = 0
            ok, image = self._cap.read()
            if not ok or image is None:
                return None
        media_time = self._pos / self._fps
        self._pos += 1
        return self._make_frame(image, media_time=media_time, metadata={"loop": self.loops_completed})

    def seek_seconds(self, seconds: float) -> None:
        if self._cap:
            self._pos = max(0, int(seconds * self._fps))
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, self._pos)

    def close(self) -> None:
        if self._cap:
            self._cap.release()
        self._cap = None
        self._opened = False

    @property
    def masked_url(self) -> str:
        return f"file://{self.path.name}"

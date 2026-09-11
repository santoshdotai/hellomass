"""Laptop / USB webcam connector."""
from __future__ import annotations

import platform
from typing import Optional

import cv2

from src.sources.base import Frame, SourceError, SourceInfo, VideoSource


class WebcamSource(VideoSource):
    kind = "webcam"

    def __init__(self, index: int = 0, name: str = "Laptop Webcam", width: int = 0, height: int = 0,
                 fps: float = 0.0):
        super().__init__(name)
        self.index = int(index)
        self.req_width, self.req_height, self.req_fps = width, height, fps
        self._cap: Optional[cv2.VideoCapture] = None

    @staticmethod
    def _backend() -> int:
        if platform.system() == "Windows":
            return cv2.CAP_DSHOW  # much faster to open than MSMF on most Windows laptops
        return cv2.CAP_ANY

    def open(self) -> SourceInfo:
        self._cap = cv2.VideoCapture(self.index, self._backend())
        if not self._cap or not self._cap.isOpened():
            self._cap = None
            raise SourceError(
                f"Webcam {self.index} could not be opened. Close other apps that may be using the camera "
                f"(Teams, Zoom, browser tabs), check the OS camera privacy setting, or try another index.")
        if self.req_width:
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.req_width)
        if self.req_height:
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.req_height)
        if self.req_fps:
            self._cap.set(cv2.CAP_PROP_FPS, self.req_fps)
        ok, image = self._cap.read()
        if not ok or image is None:
            self._cap.release()
            self._cap = None
            raise SourceError(
                f"Webcam {self.index} opened but delivered no image. Another program may hold it, "
                f"or the camera privacy shutter/setting is blocking access.")
        fps = self._cap.get(cv2.CAP_PROP_FPS) or 0.0
        self.info = SourceInfo(name=self.name, kind=self.kind, masked_url=f"webcam://{self.index}",
                               width=int(image.shape[1]), height=int(image.shape[0]),
                               fps=float(fps) if fps and fps < 240 else 30.0, is_live=True)
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
            self._cap.release()
        self._cap = None
        self._opened = False

    @property
    def masked_url(self) -> str:
        return f"webcam://{self.index}"


def probe_webcams(max_index: int = 4) -> list[dict]:
    """Quickly report which webcam indices open (used by the Settings page)."""
    found = []
    backend = WebcamSource._backend()
    for idx in range(max_index):
        cap = cv2.VideoCapture(idx, backend)
        ok = cap.isOpened()
        if ok:
            ok, _ = cap.read()
            found.append({"index": idx, "available": bool(ok),
                          "resolution": f"{int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}"})
        cap.release()
    return found

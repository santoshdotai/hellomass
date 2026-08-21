"""Object detection layer — wraps Ultralytics YOLO11 (Phase 2.1).

Model size and device are pure configuration; nothing downstream needs to
change when you switch yolo11n.pt -> yolo11s.pt/yolo11m.pt or CPU -> GPU.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from loguru import logger

from config.model_config import RELEVANT_CLASSES
from config.settings import settings


@dataclass
class Detection:
    box: tuple[float, float, float, float]  # x1,y1,x2,y2 in pixel coords
    confidence: float
    class_id: int
    class_name: str


def resolve_device() -> str:
    if settings.use_gpu == "false":
        return "cpu"
    try:
        import torch
        if settings.use_gpu in ("auto", "true") and torch.cuda.is_available():
            return "cuda"
    except Exception:  # pragma: no cover - torch always present, defensive only
        pass
    if settings.use_gpu == "true":
        logger.warning("USE_GPU=true requested but CUDA is not available — falling back to CPU")
    return "cpu"


class Detector:
    """Thin wrapper so the rest of the app never imports ultralytics directly."""

    def __init__(self, model_name: str | None = None, confidence: float = 0.35):
        self.model_name = model_name or settings.detection_model
        self.confidence = confidence
        self.device = resolve_device()
        self._model = None

    def load(self):
        from ultralytics import YOLO
        from config.model_config import get_model_path

        weights_path = get_model_path("detection", self.model_name)
        weights_path.parent.mkdir(parents=True, exist_ok=True)
        # Ultralytics auto-downloads to this exact path (matched by filename) if missing.
        logger.info(f"Loading detection model {self.model_name} on device={self.device}")
        self._model = YOLO(str(weights_path))
        return self

    @property
    def device_label(self) -> str:
        return "NVIDIA GPU" if self.device == "cuda" else "CPU"

    def detect(self, frame: np.ndarray) -> list[Detection]:
        if self._model is None:
            self.load()
        results = self._model.predict(
            frame,
            imgsz=settings.input_resolution,
            conf=self.confidence,
            device=self.device,
            classes=list(RELEVANT_CLASSES.keys()),
            verbose=False,
        )
        detections: list[Detection] = []
        if not results:
            return detections
        result = results[0]
        boxes = result.boxes
        if boxes is None:
            return detections
        for box in boxes:
            xyxy = box.xyxy[0].tolist()
            conf = float(box.conf[0])
            cls_id = int(box.cls[0])
            class_name = RELEVANT_CLASSES.get(cls_id, self._model.names.get(cls_id, str(cls_id)))
            detections.append(Detection(box=tuple(xyxy), confidence=conf, class_id=cls_id, class_name=class_name))
        return detections

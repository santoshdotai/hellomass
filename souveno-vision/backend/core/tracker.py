"""Multi-object tracking layer (Phase 2.2).

Uses Ultralytics' built-in tracker integration, which ships both ByteTrack
and BoT-SORT trackers (`bytetrack.yaml` / `botsort.yaml`) running on top of
the already-loaded detection model — no second model load, one config
switch (`TRACKER=bytetrack|botsort`) to change strategy.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from loguru import logger

from backend.core.detector import Detector
from config.model_config import RELEVANT_CLASSES
from config.settings import settings


@dataclass
class TrackedObject:
    track_id: int
    box: tuple[float, float, float, float]
    confidence: float
    class_id: int
    class_name: str


class Tracker:
    def __init__(self, detector: Detector, tracker_type: str | None = None):
        self.detector = detector
        self.tracker_type = tracker_type or settings.tracker
        self._tracker_yaml = "bytetrack.yaml" if self.tracker_type == "bytetrack" else "botsort.yaml"
        logger.info(f"Tracker initialised: {self.tracker_type} ({self._tracker_yaml})")

    def reset(self):
        """Clear tracker internal state (e.g. when starting a new session)."""
        model = self.detector._model
        if model is not None and hasattr(model, "predictor") and model.predictor is not None:
            trackers = getattr(model.predictor, "trackers", None)
            if trackers:
                for t in trackers:
                    if hasattr(t, "reset"):
                        t.reset()

    def track(self, frame: np.ndarray) -> list[TrackedObject]:
        if self.detector._model is None:
            self.detector.load()
        results = self.detector._model.track(
            frame,
            persist=True,
            imgsz=settings.input_resolution,
            conf=self.detector.confidence,
            device=self.detector.device,
            classes=list(RELEVANT_CLASSES.keys()),
            tracker=self._tracker_yaml,
            verbose=False,
        )
        tracked: list[TrackedObject] = []
        if not results:
            return tracked
        result = results[0]
        boxes = result.boxes
        if boxes is None or boxes.id is None:
            return tracked
        model_names = self.detector._model.names
        ids = boxes.id.int().tolist()
        xyxy = boxes.xyxy.tolist()
        confs = boxes.conf.tolist()
        clss = boxes.cls.int().tolist()
        for track_id, box, conf, cls_id in zip(ids, xyxy, confs, clss):
            class_name = RELEVANT_CLASSES.get(cls_id, model_names.get(cls_id, str(cls_id)))
            tracked.append(TrackedObject(track_id=track_id, box=tuple(box), confidence=float(conf),
                                          class_id=cls_id, class_name=class_name))
        return tracked

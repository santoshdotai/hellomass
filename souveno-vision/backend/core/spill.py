"""Spillage / wastage detection — Phase 13, deliberately experimental.

A generic COCO-trained YOLO model cannot reliably see liquid spills; we do
not pretend otherwise. This module defines the interface a real spill
model plugs into later (custom YOLO checkpoint, segmentation model,
vision-language model, or anomaly detector) and, until one is installed,
offers only a manual demo trigger so the UI/event pipeline can be built
and tested end-to-end honestly.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from config.settings import settings


@dataclass
class SpillCandidate:
    zone_id: str
    confidence: float
    source: str  # "manual_demo_trigger" | "custom_model" | "segmentation" | "vlm" | "anomaly_detection"
    detected_at: float = field(default_factory=time.time)


class SpillDetector:
    """Experimental module. `mode` reports honestly to the UI whether
    detections are simulated or model-driven."""

    def __init__(self, model_path: Optional[str] = None, demo_spill_mode: Optional[bool] = None):
        self.model_path = model_path or settings.spill_model_path or None
        self.demo_spill_mode = settings.demo_spill_mode if demo_spill_mode is None else demo_spill_mode
        self._manual_queue: list[SpillCandidate] = []

    @property
    def status_label(self) -> str:
        if self.model_path:
            return "Experimental — Custom Model Active"
        if self.demo_spill_mode:
            return "Experimental / Demo Spill Detection (manual trigger only)"
        return "Disabled"

    @property
    def is_model_backed(self) -> bool:
        return bool(self.model_path)

    def trigger_demo_spill(self, zone_id: str, confidence: float = 0.55) -> SpillCandidate:
        """Called by the admin/demo-mode 'Simulate Spill Event' control.
        Confidence is intentionally kept modest — never fake high certainty."""
        candidate = SpillCandidate(zone_id=zone_id, confidence=min(confidence, 0.6),
                                    source="manual_demo_trigger")
        self._manual_queue.append(candidate)
        return candidate

    def poll(self, frame=None) -> list[SpillCandidate]:
        """In a future version this method runs the configured model against
        `frame` and returns real detections. For V0.1, it only drains the
        manual demo-trigger queue."""
        if self.is_model_backed:
            # Extension point: real inference would run here and populate results.
            return []
        pending = self._manual_queue
        self._manual_queue = []
        return pending

"""Screenshot capture for important alerts (Phase 20). Deliberately avoids
storing any personal information — the frame already contains only
anonymous bounding boxes/track IDs, never names or biometric data."""
from __future__ import annotations

import cv2
import numpy as np

from backend.core.events import format_hms
from config.settings import settings


def save_event_screenshot(frame: np.ndarray, event_uid: str, event_type: str, zone_id: str | None,
                           timestamp: float) -> str:
    frame = frame.copy()
    h, w = frame.shape[:2]
    cv2.rectangle(frame, (0, h - 60), (w, h), (24, 24, 24), -1)
    cv2.putText(frame, "SOUVENO VISION", (10, h - 38), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(frame, f"{event_type}  |  {zone_id or '-'}  |  {format_hms(timestamp)}", (10, h - 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 220, 255), 1, cv2.LINE_AA)
    out_path = settings.screenshots_dir / f"{event_uid}.jpg"
    cv2.imwrite(str(out_path), frame)
    return str(out_path)

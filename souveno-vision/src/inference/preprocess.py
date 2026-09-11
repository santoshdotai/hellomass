"""Layer 2 helpers — resize / letterbox while preserving aspect ratio, and
scale detections back to the original frame."""
from __future__ import annotations

import cv2
import numpy as np


def resize_max_width(image: np.ndarray, max_width: int) -> tuple[np.ndarray, float]:
    """Downscale so width <= max_width (never upscale). Returns (image, scale)."""
    h, w = image.shape[:2]
    if max_width <= 0 or w <= max_width:
        return image, 1.0
    scale = max_width / float(w)
    resized = cv2.resize(image, (max_width, max(1, int(round(h * scale)))), interpolation=cv2.INTER_AREA)
    return resized, scale


def letterbox(image: np.ndarray, size: int = 640, color=(114, 114, 114)) -> tuple[np.ndarray, float, tuple[int, int]]:
    """Resize with unchanged aspect ratio into a size x size canvas.
    Returns (canvas, scale, (pad_x, pad_y))."""
    h, w = image.shape[:2]
    scale = min(size / float(h), size / float(w))
    nw, nh = int(round(w * scale)), int(round(h * scale))
    resized = cv2.resize(image, (nw, nh), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((size, size, 3), color, dtype=np.uint8)
    pad_x, pad_y = (size - nw) // 2, (size - nh) // 2
    canvas[pad_y:pad_y + nh, pad_x:pad_x + nw] = resized
    return canvas, scale, (pad_x, pad_y)


def unletterbox_box(box, scale: float, pad: tuple[int, int], orig_w: int, orig_h: int):
    x1, y1, x2, y2 = box
    px, py = pad
    x1, x2 = (x1 - px) / scale, (x2 - px) / scale
    y1, y2 = (y1 - py) / scale, (y2 - py) / scale
    return (max(0.0, x1), max(0.0, y1), min(float(orig_w), x2), min(float(orig_h), y2))


def scale_boxes(boxes, factor: float):
    return [(b[0] / factor, b[1] / factor, b[2] / factor, b[3] / factor) for b in boxes]

"""Frame overlay rendering: zones, virtual lines with direction arrows, person
boxes with anonymous Track IDs + confidence, dwell timers, counters and a
status strip. Pure OpenCV drawing — no business logic here."""
from __future__ import annotations

import cv2
import numpy as np

from src.analytics.spatial import FrameAnalytics
from src.analytics.zones import Zone

SEVERITY_BGR = {"low": (200, 200, 90), "medium": (0, 165, 255), "high": (0, 80, 255), "critical": (0, 0, 220)}


def hex_to_bgr(hex_color: str, default=(255, 169, 64)) -> tuple[int, int, int]:
    h = (hex_color or "").lstrip("#")
    if len(h) != 6:
        return default
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return (b, g, r)


def _px(points, w, h):
    return np.array([[int(p[0] * w), int(p[1] * h)] for p in points], dtype=np.int32)


def draw_zones(frame: np.ndarray, zones: list[Zone], zone_counts: dict[str, int] | None = None, alpha: float = 0.18) -> None:
    h, w = frame.shape[:2]
    overlay = frame.copy()
    for z in zones:
        if not z.enabled:
            continue
        color = hex_to_bgr(z.color)
        pts = _px(z.points, w, h)
        if z.is_line and len(pts) >= 2:
            a, b = tuple(pts[0]), tuple(pts[1])
            cv2.line(frame, a, b, color, 3, cv2.LINE_AA)
            # direction arrow: "in" = right side -> left side of A->B (flipped if configured)
            mx, my = (a[0] + b[0]) // 2, (a[1] + b[1]) // 2
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = max(1.0, (dx * dx + dy * dy) ** 0.5)
            nx, ny = -dy / length, dx / length  # left normal
            sign = -1 if z.direction_flipped else 1
            tip = (int(mx + nx * 28 * sign), int(my + ny * 28 * sign))
            tail = (int(mx - nx * 28 * sign), int(my - ny * 28 * sign))
            cv2.arrowedLine(frame, tail, tip, color, 2, cv2.LINE_AA, tipLength=0.35)
            cv2.putText(frame, f"{z.name}  ({z.in_label} ->)", (a[0] + 6, a[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA)
        elif len(pts) >= 3:
            cv2.fillPoly(overlay, [pts], color)
            cv2.polylines(frame, [pts], True, color, 2, cv2.LINE_AA)
            label = z.name.upper() if z.kind == "restricted" else z.name
            if zone_counts is not None and z.kind == "occupancy":
                label += f"  {zone_counts.get(z.zone_id, 0)}" + (f"/{z.occupancy_limit}" if z.occupancy_limit else "")
            x, y = int(pts[:, 0].min()) + 6, int(pts[:, 1].min()) + 20
            cv2.putText(frame, label, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(frame, label, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1, cv2.LINE_AA)
    cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)


def draw_tracks(frame: np.ndarray, fa: FrameAnalytics, show_trails: bool = False) -> None:
    for tv in fa.tracks:
        x1, y1, x2, y2 = [int(v) for v in tv.box]
        color = (0, 60, 255) if tv.in_restricted else (80, 220, 120)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        title = f"Person {tv.track_id}  {tv.confidence * 100:.0f}%"
        (tw, th), _ = cv2.getTextSize(title, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(frame, (x1, max(0, y1 - th - 8)), (x1 + tw + 8, y1), color, -1)
        cv2.putText(frame, title, (x1 + 4, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (10, 10, 10), 1, cv2.LINE_AA)
        if tv.dwell:
            zid, secs = max(tv.dwell.items(), key=lambda kv: kv[1])
            name = fa.zones[zid].name if zid in fa.zones else zid
            cv2.putText(frame, f"{name}: {secs:.0f}s", (x1, min(frame.shape[0] - 4, y2 + 16)), cv2.FONT_HERSHEY_SIMPLEX,
                        0.45, (255, 255, 255), 1, cv2.LINE_AA)
        if show_trails and len(tv.trail) >= 2:
            cv2.polylines(frame, [np.array(tv.trail, dtype=np.int32)], False, (255, 210, 90), 2, cv2.LINE_AA)
        cv2.circle(frame, (int((x1 + x2) / 2), y2), 4, color, -1)


def draw_status_strip(frame: np.ndarray, source_name: str, status: str, device: str, fps: float, fa: FrameAnalytics | None,
                      clock_text: str, demo_mode: bool = False) -> None:
    h, w = frame.shape[:2]
    cv2.rectangle(frame, (0, 0), (w, 30), (18, 18, 22), -1)
    status_color = {"live": (90, 220, 120), "degraded": (0, 190, 255), "connecting": (255, 200, 60)}.get(status, (0, 70, 255))
    cv2.circle(frame, (14, 15), 6, status_color, -1)
    clock_short = clock_text.split(" ")[-1] if " " in clock_text else clock_text
    (cw, _), _ = cv2.getTextSize(clock_short, cv2.FONT_HERSHEY_SIMPLEX, 0.52, 1)
    left = f"SOUVENO AI  |  {source_name}  |  {status.upper()}  |  {device}  |  {fps:.1f} fps"
    (lw, _), _ = cv2.getTextSize(left, cv2.FONT_HERSHEY_SIMPLEX, 0.52, 1)
    if 28 + lw + cw + 24 > w:  # narrow frame: drop the least important parts so nothing overlaps
        left = f"SOUVENO AI | {source_name[:18]} | {status.upper()} | {fps:.1f} fps"
        (lw, _), _ = cv2.getTextSize(left, cv2.FONT_HERSHEY_SIMPLEX, 0.52, 1)
        if 28 + lw + cw + 24 > w:
            left = f"SOUVENO AI | {status.upper()} | {fps:.1f} fps"
    cv2.putText(frame, left, (28, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (235, 235, 235), 1, cv2.LINE_AA)
    cv2.putText(frame, clock_short, (w - cw - 10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (180, 220, 255), 1, cv2.LINE_AA)
    if fa is not None:
        counts = f"People {fa.people_visible}   Entries {fa.entries}   Exits {fa.exits}   Occupancy {fa.occupancy}"
        (tw, th), _ = cv2.getTextSize(counts, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(frame, (0, h - th - 18), (tw + 20, h), (18, 18, 22), -1)
        cv2.putText(frame, counts, (10, h - 9), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
    if demo_mode:
        cv2.putText(frame, "DEMO", (w - 70, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (60, 160, 255), 2, cv2.LINE_AA)


def draw_message(frame: np.ndarray, title: str, detail: str = "") -> None:
    h, w = frame.shape[:2]
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, h // 2 - 50), (w, h // 2 + 50), (10, 10, 10), -1)
    cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)
    cv2.putText(frame, title, (30, h // 2 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
    if detail:
        cv2.putText(frame, detail[:110], (30, h // 2 + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1, cv2.LINE_AA)


def placeholder_frame(width: int = 960, height: int = 540, title: str = "No source running", detail: str = "") -> np.ndarray:
    frame = np.full((height, width, 3), (30, 32, 36), dtype=np.uint8)
    draw_message(frame, title, detail)
    return frame

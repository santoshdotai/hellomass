"""Event clip generation (Phase 19). Clips are generated on demand (first
'VIEW CLIP' request) by re-reading the original recorded file — the demo
never needs an always-on frame ring-buffer, which keeps the live pipeline
simple and works identically once Stage 3 swaps in a live camera (clips
would instead be cut from a short rolling buffer maintained by the edge
process — a detail that stays entirely inside this module)."""
from __future__ import annotations

import cv2

from config.settings import settings


def _burn_caption(frame, event_type: str, zone_id: str | None, elapsed_label: str):
    h, w = frame.shape[:2]
    cv2.rectangle(frame, (0, 0), (w, 30), (24, 24, 24), -1)
    text = f"SOUVENO VISION | {event_type} | {zone_id or '-'} | {elapsed_label}"
    cv2.putText(frame, text, (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)


def generate_event_clip(source_path: str, event_uid: str, event_type: str, zone_id: str | None,
                         start_time: float, end_time: float | None, pre_seconds: float = 5.0,
                         post_seconds: float = 5.0) -> str:
    out_path = settings.clips_dir / f"{event_uid}.mp4"
    if out_path.exists():
        return str(out_path)

    cap = cv2.VideoCapture(source_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open source video for clip generation: {source_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    start_sec = max(0.0, start_time - pre_seconds)
    end_sec = (end_time if end_time is not None else start_time) + post_seconds
    start_frame = int(start_sec * fps)
    end_frame = int(end_sec * fps)
    if total_frames:
        end_frame = min(end_frame, total_frames)

    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_path), fourcc, fps, (width, height))

    frame_idx = start_frame
    while frame_idx < end_frame:
        ok, frame = cap.read()
        if not ok:
            break
        elapsed = frame_idx / fps
        _burn_caption(frame, event_type, zone_id, f"{elapsed:0.1f}s")
        writer.write(frame)
        frame_idx += 1

    writer.release()
    cap.release()
    return str(out_path)

"""Phases 3, 5-13, 17-21 — starts a live analysis session over the
uploaded MP4 and streams annotated frames + intelligence to the dashboard
over a WebSocket.

This loop is the only thing that changes when Stage 3 swaps in a live
RTSP camera: replace `FileVideoSource(...)` with `RTSPVideoSource(...)`
(an `is_live` stream simply never reaches the "completed" branch) — the
detector/tracker/zone/rule/event/metrics stack underneath is unchanged.
"""
from __future__ import annotations

import asyncio
import base64
import json
import time

import cv2
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from loguru import logger
from sqlalchemy.orm import Session

from backend.core.ai_summary import generate_summary
from backend.core.detector import Detector
from backend.core.notifications import AlertMessage, get_notification_service
from backend.core.pipeline import VisionPipeline
from backend.core.tracker import Tracker
from backend.core.video_source import FileVideoSource
from backend.core.zones import DEFAULT_ZONES, zone_defs_from_records
from backend.db import crud, models
from backend.db.database import SessionLocal, get_db
from backend.services.screenshot_generator import save_event_screenshot
from config.settings import settings

router = APIRouter(prefix="/api/sessions", tags=["analysis"])
ws_router = APIRouter(tags=["analysis-ws"])

_detector: Detector | None = None


def get_shared_detector() -> Detector:
    """One model load shared across sessions — YOLO load time is several
    seconds and there is no reason to pay it more than once per process."""
    global _detector
    if _detector is None:
        _detector = Detector().load()
    return _detector


@router.post("/{session_id}/start")
def start_analysis(session_id: int, db: Session = Depends(get_db)):
    s = crud.get_session(db, session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    crud.update_session_status(db, session_id, "analyzing")
    return {"status": "analyzing", "session_id": session_id, "websocket_url": f"/ws/analysis/{session_id}"}


@router.get("/{session_id}/summary")
def get_summary_endpoint(session_id: int, db: Session = Depends(get_db)):
    if not crud.get_session(db, session_id):
        raise HTTPException(404, "Session not found")
    summary = crud.get_summary(db, session_id)
    if not summary:
        raise HTTPException(400, "No summary yet — finish an analysis run first")
    return {
        "summary_text": summary.ai_summary_text,
        "stats": json.loads(summary.stats_json),
        "generated_by": summary.generated_by,
    }


def _attach_screenshot(db: Session, event_uid: str, path: str):
    ev = db.query(models.Event).filter(models.Event.event_uid == event_uid).first()
    if ev:
        ev.screenshot_path = path
        db.commit()


async def _handle_control_message(raw: str, pipeline: VisionPipeline, control_state: dict):
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        return
    action = msg.get("action")
    now = pipeline.last_timestamp
    if action == "set_role":
        pipeline.set_role(int(msg["track_id"]), msg["role"])
    elif action == "trigger_spill":
        pipeline.trigger_spill(msg.get("zone_id"), now, confidence=float(msg.get("confidence", 0.55)))
    elif action == "resolve_spill":
        pipeline.resolve_spill(msg["spill_id"], now)
    elif action == "pause":
        control_state["paused"] = True
    elif action == "resume":
        control_state["paused"] = False


def _finalize_session(db: Session, session_id: int, pipeline: VisionPipeline, duration_seconds: float):
    now = pipeline.last_timestamp or duration_seconds
    for key in list(pipeline.rule_engine._idle_open):
        pipeline.event_engine.close_event(key, now)
    for key in list(pipeline.rule_engine._table_open):
        pipeline.event_engine.close_event(key, now)
    for key in list(pipeline.rule_engine._pickup_open):
        pipeline.event_engine.close_event(key, now)
    for zone_id, level in list(pipeline.rule_engine._queue_level.items()):
        if level != "normal":
            pipeline.event_engine.close_event(f"queue_{level}:{zone_id}", now)
    for spill_id in list(pipeline._active_spills.keys()):
        pipeline.resolve_spill(spill_id, now)
    for meta in pipeline.track_meta.values():
        entered = meta.get("queue_entered_at")
        if entered is not None:
            pipeline.metrics.record_queue_dwell(now - entered)

    events_dicts = [crud.event_to_dict(e) for e in crud.list_events(db, session_id)]
    result = generate_summary(duration_seconds or now, pipeline.metrics.snapshot(), events_dicts)
    crud.save_summary(db, session_id, result["stats"], result["summary_text"], result["generated_by"])
    crud.update_session_status(db, session_id, "completed")


@ws_router.websocket("/ws/analysis/{session_id}")
async def analysis_ws(websocket: WebSocket, session_id: int):
    await websocket.accept()
    db = SessionLocal()
    stopped = False
    try:
        session = crud.get_session(db, session_id)
        if not session:
            await websocket.send_json({"type": "error", "message": "Session not found"})
            await websocket.close()
            return

        zone_rows = crud.get_zones_for_session(db, session_id)
        if not zone_rows:
            crud.save_zones(db, session_id, None, DEFAULT_ZONES)
            zone_rows = crud.get_zones_for_session(db, session_id)
        zone_defs = zone_defs_from_records([crud.zone_to_dict(z) for z in zone_rows])

        detector = get_shared_detector()
        tracker = Tracker(detector)
        tracker.reset()

        notifier = get_notification_service()

        def alert_hook(alert: dict):
            notifier.notify(
                AlertMessage(title=alert["title"], body=f"Zone: {alert['zone_id']} | Started {alert['started']}",
                             severity=alert["severity"]),
                dedupe_key=f"{session_id}:{alert['event_type']}:{alert['zone_id']}",
            )

        pipeline = VisionPipeline(db, session_id, session.camera_id, zone_defs, detector, tracker,
                                   session.width, session.height, demo_mode=session.demo_mode,
                                   alert_hook=alert_hook)
        pipeline.last_timestamp = 0.0

        source = FileVideoSource(session.file_path)
        info = source.open()

        crud.update_session_status(db, session_id, "analyzing")
        await websocket.send_json({
            "type": "started",
            "video_info": {"fps": info.fps, "width": info.width, "height": info.height,
                            "duration_seconds": info.duration_seconds},
            "zones": [crud.zone_to_dict(z) for z in zone_rows],
            "demo_mode": settings.demo_mode,
        })

        process_every_n = max(1, settings.process_every_n_frames)
        control_state = {"paused": False}
        frame_iter = source.frames()
        last_snapshot_time = -10.0

        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=0.005)
                await _handle_control_message(raw, pipeline, control_state)
            except asyncio.TimeoutError:
                pass

            if control_state["paused"]:
                await asyncio.sleep(0.1)
                continue

            frame_start = time.time()
            try:
                frame_idx, ts, frame = next(frame_iter)
            except StopIteration:
                break

            if frame_idx % process_every_n != 0:
                continue

            pipeline.last_timestamp = ts
            result, annotated = await asyncio.to_thread(pipeline.process_frame, frame, frame_idx, ts)

            for ev in result["new_events"]:
                if ev["severity"] in ("warning", "critical") and ev["status"] in ("open", "closed"):
                    try:
                        path = save_event_screenshot(annotated, ev["event_id"], ev["event_type"],
                                                       ev["zone_id"], ts)
                        _attach_screenshot(db, ev["event_id"], path)
                    except Exception:
                        logger.exception("Screenshot generation failed")

            ok, buf = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 78])
            if not ok:
                continue
            b64 = base64.b64encode(buf.tobytes()).decode("ascii")

            if ts - last_snapshot_time >= 2.0:
                crud.save_metric_snapshot(db, session_id, ts, result["metrics"])
                last_snapshot_time = ts

            await websocket.send_json({"type": "frame", "image": f"data:image/jpeg;base64,{b64}", "payload": result})

            elapsed = time.time() - frame_start
            target_interval = process_every_n / (info.fps or 25.0)
            if elapsed < target_interval:
                await asyncio.sleep(target_interval - elapsed)

        source.release()
        _finalize_session(db, session_id, pipeline, info.duration_seconds)
        await websocket.send_json({"type": "completed"})
        await websocket.close()

    except WebSocketDisconnect:
        stopped = True
    except Exception as exc:  # pragma: no cover - defensive, surfaced to client when possible
        logger.exception("Analysis websocket error")
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
    finally:
        db.close()
        logger.info(f"Analysis websocket closed for session {session_id} (client_disconnected={stopped})")

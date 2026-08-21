"""Phase 3 — video upload / session lifecycle."""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import cv2
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from loguru import logger
from sqlalchemy.orm import Session

from backend.db import crud
from backend.db.database import get_db
from config.settings import settings

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}
MAX_UPLOAD_BYTES = 1024 * 1024 * 1024  # 1 GB


@router.post("/upload")
async def upload_video(file: UploadFile = File(...), db: Session = Depends(get_db)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported format '{suffix}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}")

    safe_name = f"{uuid.uuid4().hex[:10]}{suffix}"
    dest_path = settings.uploads_dir / safe_name
    size = 0
    with dest_path.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                out.close()
                dest_path.unlink(missing_ok=True)
                raise HTTPException(400, "File too large (limit 1GB for the demo)")
            out.write(chunk)

    cap = cv2.VideoCapture(str(dest_path))
    if not cap.isOpened():
        dest_path.unlink(missing_ok=True)
        raise HTTPException(400, "Could not read this video file — is it a valid MP4/MOV/AVI/MKV?")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps else 0
    cap.release()

    if width == 0 or height == 0:
        dest_path.unlink(missing_ok=True)
        raise HTTPException(400, "Video has no readable frames")

    session = crud.create_session(
        db, filename=file.filename or safe_name, file_path=str(dest_path), fps=fps,
        width=width, height=height, duration_seconds=duration, total_frames=total_frames,
        demo_mode=settings.demo_mode,
    )
    logger.info(f"Video session {session.session_uid} created from '{file.filename}' "
                f"({width}x{height} @ {fps:.1f}fps, {duration:.1f}s)")

    return _session_dict(session)


def _session_dict(s) -> dict:
    return {
        "session_id": s.id, "session_uid": s.session_uid, "filename": s.filename,
        "fps": s.fps, "width": s.width, "height": s.height, "duration_seconds": s.duration_seconds,
        "total_frames": s.total_frames, "status": s.status, "demo_mode": s.demo_mode,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


@router.get("")
def list_sessions(db: Session = Depends(get_db)):
    return [_session_dict(s) for s in crud.list_sessions(db)]


@router.get("/{session_id}")
def get_session(session_id: int, db: Session = Depends(get_db)):
    s = crud.get_session(db, session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    return _session_dict(s)


@router.get("/{session_id}/frame")
def get_frame(session_id: int, seconds: float = 1.0, db: Session = Depends(get_db)):
    """Grab a single frame (JPEG) for the zone builder canvas."""
    s = crud.get_session(db, session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    cap = cv2.VideoCapture(s.file_path)
    if not cap.isOpened():
        raise HTTPException(500, "Could not reopen source video")
    frame_no = max(0, int(seconds * (s.fps or 25)))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise HTTPException(500, "Could not read a frame at that timestamp")
    ok, buf = cv2.imencode(".jpg", frame)
    if not ok:
        raise HTTPException(500, "Could not encode frame")
    return Response(content=buf.tobytes(), media_type="image/jpeg")


@router.post("/{session_id}/reset")
def reset_session(session_id: int, db: Session = Depends(get_db)):
    """Demo Mode 'reset all data' button (Phase 24)."""
    s = crud.get_session(db, session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    from backend.db import models
    db.query(models.Event).filter(models.Event.session_id == session_id).delete()
    db.query(models.Alert).filter(models.Alert.session_id == session_id).delete()
    db.query(models.MetricSnapshot).filter(models.MetricSnapshot.session_id == session_id).delete()
    db.query(models.Track).filter(models.Track.session_id == session_id).delete()
    db.query(models.DailySummary).filter(models.DailySummary.session_id == session_id).delete()
    s.status = "ready"
    s.completed_at = None
    db.commit()
    return {"status": "reset", "session_id": session_id}

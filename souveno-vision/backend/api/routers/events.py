"""Phase 14/18/19/20 — event list, timeline, clips, screenshots."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.db import crud
from backend.db.database import get_db
from backend.services.clip_generator import generate_event_clip

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("/session/{session_id}")
def list_session_events(session_id: int, db: Session = Depends(get_db)):
    if not crud.get_session(db, session_id):
        raise HTTPException(404, "Session not found")
    events = crud.list_events(db, session_id)
    return {"events": [crud.event_to_dict(e) for e in events]}


@router.get("/{event_uid}/clip")
def get_event_clip(event_uid: str, db: Session = Depends(get_db)):
    from backend.db import models
    event = db.query(models.Event).filter(models.Event.event_uid == event_uid).first()
    if not event:
        raise HTTPException(404, "Event not found")
    session = crud.get_session(db, event.session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    try:
        clip_path = generate_event_clip(
            source_path=session.file_path, event_uid=event.event_uid, event_type=event.event_type,
            zone_id=event.zone_id, start_time=event.start_time_seconds, end_time=event.end_time_seconds,
        )
    except RuntimeError as exc:
        raise HTTPException(500, str(exc))

    event.clip_path = clip_path
    db.commit()
    return FileResponse(clip_path, media_type="video/mp4", filename=Path(clip_path).name)


@router.get("/{event_uid}/screenshot")
def get_event_screenshot(event_uid: str, db: Session = Depends(get_db)):
    from backend.db import models
    event = db.query(models.Event).filter(models.Event.event_uid == event_uid).first()
    if not event or not event.screenshot_path or not Path(event.screenshot_path).exists():
        raise HTTPException(404, "Screenshot not available for this event")
    return FileResponse(event.screenshot_path, media_type="image/jpeg")

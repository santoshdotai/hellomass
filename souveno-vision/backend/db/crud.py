"""Thin CRUD helpers over the SQLAlchemy models. Kept intentionally simple —
this is a demo data layer, not an ORM abstraction framework."""
import json
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from backend.db import models


# ---------------------------------------------------------------- sessions
def create_session(db: Session, filename: str, file_path: str, fps: float, width: int,
                    height: int, duration_seconds: float, total_frames: int, demo_mode: bool) -> models.VideoSession:
    obj = models.VideoSession(
        filename=filename, file_path=file_path, fps=fps, width=width, height=height,
        duration_seconds=duration_seconds, total_frames=total_frames, demo_mode=demo_mode,
        status="ready",
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def get_session(db: Session, session_id: int) -> Optional[models.VideoSession]:
    return db.query(models.VideoSession).filter(models.VideoSession.id == session_id).first()


def list_sessions(db: Session):
    return db.query(models.VideoSession).order_by(models.VideoSession.created_at.desc()).all()


def update_session_status(db: Session, session_id: int, status: str):
    obj = get_session(db, session_id)
    if obj:
        obj.status = status
        if status == "completed":
            obj.completed_at = datetime.utcnow()
        db.commit()
    return obj


# ---------------------------------------------------------------- zones
def save_zones(db: Session, session_id: Optional[int], preset_name: Optional[str], zones: list[dict]):
    if session_id is not None:
        db.query(models.Zone).filter(models.Zone.session_id == session_id).delete()
    elif preset_name:
        db.query(models.Zone).filter(models.Zone.preset_name == preset_name).delete()
    created = []
    for z in zones:
        obj = models.Zone(
            session_id=session_id,
            preset_name=preset_name,
            name=z["name"],
            zone_type=z["zone_type"],
            shape_type=z.get("shape_type", "polygon"),
            points_json=json.dumps(z["points"]),
            color=z.get("color", "#3ba7ff"),
        )
        db.add(obj)
        created.append(obj)
    db.commit()
    for obj in created:
        db.refresh(obj)
    return created


def get_zones_for_session(db: Session, session_id: int):
    return db.query(models.Zone).filter(models.Zone.session_id == session_id).all()


def get_zone_presets(db: Session):
    rows = db.query(models.Zone.preset_name).filter(models.Zone.preset_name.isnot(None)).distinct().all()
    return [r[0] for r in rows]


def get_zones_by_preset(db: Session, preset_name: str):
    return db.query(models.Zone).filter(models.Zone.preset_name == preset_name).all()


def zone_to_dict(z: models.Zone) -> dict:
    return {
        "id": z.id,
        "name": z.name,
        "zone_type": z.zone_type,
        "shape_type": z.shape_type,
        "points": json.loads(z.points_json),
        "color": z.color,
    }


# ---------------------------------------------------------------- events
def create_event(db: Session, session_id: int, camera_id: str, event_type: str, zone_id: str,
                  track_ids: list[int], start_time_seconds: float, severity: str = "info",
                  confidence: float = 1.0, metadata: Optional[dict] = None) -> models.Event:
    obj = models.Event(
        session_id=session_id, camera_id=camera_id, event_type=event_type, zone_id=zone_id,
        track_ids_json=json.dumps(track_ids), start_time_seconds=start_time_seconds,
        severity=severity, confidence=confidence, metadata_json=json.dumps(metadata or {}),
        status="open",
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def close_event(db: Session, event_id: int, end_time_seconds: float):
    obj = db.query(models.Event).filter(models.Event.id == event_id).first()
    if obj and obj.status == "open":
        obj.end_time_seconds = end_time_seconds
        obj.duration_seconds = max(0.0, end_time_seconds - obj.start_time_seconds)
        obj.status = "closed"
        db.commit()
        db.refresh(obj)
    return obj


def list_events(db: Session, session_id: int):
    return db.query(models.Event).filter(models.Event.session_id == session_id).order_by(models.Event.start_time_seconds).all()


def event_to_dict(e: models.Event) -> dict:
    return {
        "event_id": e.event_uid,
        "session_id": e.session_id,
        "camera_id": e.camera_id,
        "event_type": e.event_type,
        "zone_id": e.zone_id,
        "track_ids": json.loads(e.track_ids_json),
        "start_time": e.start_time_seconds,
        "end_time": e.end_time_seconds,
        "duration_seconds": e.duration_seconds,
        "confidence": e.confidence,
        "severity": e.severity,
        "status": e.status,
        "metadata": json.loads(e.metadata_json),
        "clip_path": e.clip_path,
        "screenshot_path": e.screenshot_path,
    }


# ---------------------------------------------------------------- alerts
def create_alert(db: Session, session_id: int, event_id: Optional[int], alert_type: str,
                  title: str, message: str, severity: str) -> models.Alert:
    obj = models.Alert(session_id=session_id, event_id=event_id, alert_type=alert_type,
                        title=title, message=message, severity=severity, active=True)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def resolve_alert(db: Session, alert_id: int):
    obj = db.query(models.Alert).filter(models.Alert.id == alert_id).first()
    if obj:
        obj.active = False
        obj.resolved_at = datetime.utcnow()
        db.commit()
    return obj


def list_active_alerts(db: Session, session_id: int):
    return db.query(models.Alert).filter(models.Alert.session_id == session_id, models.Alert.active == True).all()  # noqa: E712


# ---------------------------------------------------------------- metrics
def save_metric_snapshot(db: Session, session_id: int, video_time_seconds: float, metrics: dict):
    obj = models.MetricSnapshot(session_id=session_id, video_time_seconds=video_time_seconds,
                                 metrics_json=json.dumps(metrics))
    db.add(obj)
    db.commit()


# ---------------------------------------------------------------- settings (generic KV)
def get_setting(db: Session, key: str, default=None):
    obj = db.query(models.Setting).filter(models.Setting.key == key).first()
    if not obj:
        return default
    try:
        return json.loads(obj.value)
    except (json.JSONDecodeError, TypeError):
        return obj.value


def set_setting(db: Session, key: str, value):
    obj = db.query(models.Setting).filter(models.Setting.key == key).first()
    serialized = json.dumps(value)
    if obj:
        obj.value = serialized
    else:
        obj = models.Setting(key=key, value=serialized)
        db.add(obj)
    db.commit()


# ---------------------------------------------------------------- daily summary
def save_summary(db: Session, session_id: int, stats: dict, ai_text: str, generated_by: str):
    obj = models.DailySummary(session_id=session_id, stats_json=json.dumps(stats),
                               ai_summary_text=ai_text, generated_by=generated_by)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def get_summary(db: Session, session_id: int):
    return db.query(models.DailySummary).filter(models.DailySummary.session_id == session_id).order_by(models.DailySummary.id.desc()).first()

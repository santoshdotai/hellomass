"""Phase 4 — zone builder API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db import crud
from backend.db.database import get_db
from backend.schemas.api_schemas import ZonesSaveRequest
from config.rules_config import ZONE_TYPES
from config.settings import settings
from backend.core.zones import DEFAULT_ZONES, DEFAULT_ZONE_PRESET

router = APIRouter(prefix="/api/zones", tags=["zones"])


@router.get("/types")
def zone_types():
    return {"zone_types": ZONE_TYPES}


@router.get("/defaults")
def default_zones():
    return {"preset_name": DEFAULT_ZONE_PRESET, "zones": DEFAULT_ZONES}


@router.get("/presets")
def list_presets(db: Session = Depends(get_db)):
    return {"presets": crud.get_zone_presets(db)}


@router.get("/presets/{preset_name}")
def get_preset(preset_name: str, db: Session = Depends(get_db)):
    zones = crud.get_zones_by_preset(db, preset_name)
    return {"preset_name": preset_name, "zones": [crud.zone_to_dict(z) for z in zones]}


@router.get("/session/{session_id}")
def get_session_zones(session_id: int, db: Session = Depends(get_db)):
    zones = crud.get_zones_for_session(db, session_id)
    return {"session_id": session_id, "zones": [crud.zone_to_dict(z) for z in zones]}


@router.post("")
def save_zones(payload: ZonesSaveRequest, db: Session = Depends(get_db)):
    if payload.session_id is None and not payload.preset_name:
        raise HTTPException(400, "Provide session_id and/or preset_name")
    if payload.session_id is not None and not crud.get_session(db, payload.session_id):
        raise HTTPException(404, "Session not found")

    zones = [z.model_dump() for z in payload.zones]
    saved = crud.save_zones(db, payload.session_id, payload.preset_name, zones)
    return {"saved": len(saved), "zones": [crud.zone_to_dict(z) for z in saved]}


@router.get("/config")
def zone_config():
    return {"demo_mode": settings.demo_mode, "zone_types": ZONE_TYPES}

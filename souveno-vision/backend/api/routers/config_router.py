"""Phase 15/26 — model manager + rule configuration."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.core.detector import resolve_device
from backend.db import crud
from backend.db.database import get_db
from backend.schemas.api_schemas import RuleUpdate
from config.model_config import CURRENT_MODEL_CONFIG
from config.rules_config import DEFAULT_RULES, get_active_thresholds
from config.settings import settings

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("/models")
def model_status():
    device = resolve_device()
    return {
        "detection_model": CURRENT_MODEL_CONFIG["detection_model"],
        "tracker": CURRENT_MODEL_CONFIG["tracker"],
        "pose_enabled": CURRENT_MODEL_CONFIG["enable_pose"],
        "segmentation_enabled": CURRENT_MODEL_CONFIG["enable_segmentation"],
        "spill_model": CURRENT_MODEL_CONFIG["spill_model"],
        "inference_device": "NVIDIA GPU" if device == "cuda" else "CPU",
        "device_raw": device,
    }


@router.get("/rules")
def get_rules(db: Session = Depends(get_db)):
    overrides = crud.get_setting(db, "rule_overrides", {})
    thresholds = get_active_thresholds()
    rules = []
    for rule in DEFAULT_RULES:
        r = dict(rule)
        override = overrides.get(rule["rule_name"], {})
        r["threshold_seconds"] = override.get("threshold_seconds", thresholds.get(rule["threshold_key"]))
        r["enabled"] = override.get("enabled", rule["enabled"])
        rules.append(r)
    return {"demo_mode": settings.demo_mode, "rules": rules}


@router.post("/rules")
def update_rule(payload: RuleUpdate, db: Session = Depends(get_db)):
    overrides = crud.get_setting(db, "rule_overrides", {})
    entry = overrides.get(payload.rule_name, {})
    if payload.threshold_seconds is not None:
        entry["threshold_seconds"] = payload.threshold_seconds
    if payload.enabled is not None:
        entry["enabled"] = payload.enabled
    overrides[payload.rule_name] = entry
    crud.set_setting(db, "rule_overrides", overrides)
    return {"rule_name": payload.rule_name, "updated": entry}


@router.get("/demo-mode")
def demo_mode_status():
    return {"demo_mode": settings.demo_mode, "thresholds": get_active_thresholds()}

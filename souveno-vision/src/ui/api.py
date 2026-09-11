"""JSON / MJPEG / WebSocket API for the dashboard (all under /api/vi and /ws/vi)."""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response, StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field

from src.analytics.zones import ZONE_KINDS
from src.rules.models import RULE_TITLES, RuleType
from src.security.redaction import safe_filename
from src.sources.base import SourceError
from src.sources.factory import FUTURE_CONNECTORS, SOURCE_TYPES
from src.sources.synthetic import default_synthetic_zones
from src.sources.video_file import SUPPORTED_EXTENSIONS
from src.ui.components import PRIVACY_STATEMENT, demo_layout_zones, event_view, list_video_assets
from src.utils.time_utils import utc_iso

router = APIRouter(prefix="/api/vi", tags=["vision-intelligence"])
ws_router = APIRouter(tags=["vision-intelligence-ws"])


def ctx(request: Request):
    return request.app.state.ctx


def _tz(c) -> str:
    return c.cfg.app.get("timezone", "local")


# ------------------------------------------------------------------ models
class SourceStart(BaseModel):
    type: str = "synthetic"
    name: Optional[str] = None
    index: Optional[int] = None
    path: Optional[str] = None
    loop: bool = True
    url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    stream_profile: str = "main"
    transport: str = "tcp"
    fps: Optional[float] = None


class PauseRequest(BaseModel):
    paused: bool


class ZonesSave(BaseModel):
    source_id: Optional[str] = None
    zones: list[dict[str, Any]] = Field(default_factory=list)


class RulesSave(BaseModel):
    rules: list[dict[str, Any]]


class EventAction(BaseModel):
    actor: str = "operator"
    note: str = ""


class AuditStart(BaseModel):
    spec: SourceStart
    duration_seconds: float = 8.0


class DemoAction(BaseModel):
    seconds: Optional[float] = None
    rule_type: Optional[str] = None
    index: Optional[int] = None
    path: Optional[str] = None


# ------------------------------------------------------------------ health / state
@router.get("/health")
def health(request: Request):
    c = ctx(request)
    snap = c.health.snapshot()
    st = c.pipeline.state()
    det = c.pipeline.detector
    return {
        "status": "ok", "app": c.cfg.app.name, "brand": c.cfg.app.brand, "tagline": c.cfg.app.tagline,
        "time": st["time"], "demo_mode": st["demo_mode"], "source": st["source"], "ai": st["ai"],
        "health": snap, "database": c.db.status(), "evidence": c.evidence.status(), "webhook": c.webhook.status(),
        "detector": det.info() if det else {"backend": "not loaded"},
        "tracker": c.pipeline.tracker.info() if c.pipeline.tracker else {"backend": "-"},
        "rules": c.pipeline.rules_engine.summary(), "log_file": str(c.log_path) if c.log_path else None,
        "gpu": __import__("src.inference.detector", fromlist=["detect_gpu"]).detect_gpu(),
        "privacy": PRIVACY_STATEMENT,
    }


@router.get("/health/logs")
def health_logs(request: Request, limit: int = 120):
    return {"logs": ctx(request).repos.health.recent(limit)}


@router.get("/state")
def state(request: Request, since: Optional[str] = None):
    c = ctx(request)
    st = c.pipeline.state()
    recent = [event_view(e, _tz(c)) for e in c.events.recent(30)]
    if since:
        recent = [e for e in recent if e["timestamp"] > since]
    st["recent_events"] = recent
    st["stats"] = c.events.stats_today()
    st["privacy"] = PRIVACY_STATEMENT
    return st


# ------------------------------------------------------------------ video
@router.get("/stream.mjpg")
async def stream(request: Request, fps: float = 12.0):
    c = ctx(request)
    boundary = "souvenoframe"
    interval = 1.0 / max(1.0, min(fps, 25.0))

    async def gen():
        last = None
        while True:
            if await request.is_disconnected():
                break
            jpeg = c.pipeline.latest_jpeg()
            if jpeg is not last and jpeg:
                last = jpeg
                yield (f"--{boundary}\r\nContent-Type: image/jpeg\r\nContent-Length: {len(jpeg)}\r\n\r\n").encode() + jpeg + b"\r\n"
            await asyncio.sleep(interval)

    return StreamingResponse(gen(), media_type=f"multipart/x-mixed-replace; boundary={boundary}",
                             headers={"Cache-Control": "no-cache, no-store", "Pragma": "no-cache"})


@router.get("/snapshot.jpg")
def snapshot(request: Request, raw: int = 1):
    c = ctx(request)
    data = c.pipeline.snapshot_jpeg(raw=bool(raw)) if raw else c.pipeline.latest_jpeg()
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


# ------------------------------------------------------------------ sources
@router.get("/source")
def get_source(request: Request):
    c = ctx(request)
    st = c.pipeline.state()
    assets = list_video_assets([c.demo_assets_dir, c.uploads_dir], c.base_dir)
    return {"current": st["source"], "running": st["running"], "saved": c.repos.sources.list(), "types": SOURCE_TYPES,
            "future_connectors": FUTURE_CONNECTORS, "assets": assets,
            "rtsp_env_configured": bool(__import__("os").environ.get(c.cfg.source.rtsp.url_env, "")),
            "config_default": c.cfg.source.to_dict()}


@router.post("/source/start")
def start_source(payload: SourceStart, request: Request):
    c = ctx(request)
    spec = {k: v for k, v in payload.model_dump().items() if v is not None}
    try:
        st = c.pipeline.start(spec)
    except SourceError as exc:
        logger.warning(f"Source start failed: {exc}")
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.exception("Source start failed")
        raise HTTPException(500, f"Could not start source: {type(exc).__name__}")
    return {"ok": True, "state": st}


@router.post("/source/stop")
def stop_source(request: Request):
    ctx(request).pipeline.stop()
    return {"ok": True}


@router.post("/source/restart")
def restart_source(request: Request):
    c = ctx(request)
    if not c.pipeline.source_spec:
        raise HTTPException(400, "No source has been started yet")
    try:
        return {"ok": True, "state": c.pipeline.restart()}
    except SourceError as exc:
        raise HTTPException(400, str(exc))


@router.post("/source/pause")
def pause_source(payload: PauseRequest, request: Request):
    ctx(request).pipeline.set_paused(payload.paused)
    return {"ok": True, "paused": payload.paused}


@router.get("/source/webcams")
def webcams(request: Request, max_index: int = 4):
    c = ctx(request)
    if c.pipeline.source and c.pipeline.source.kind == "webcam":
        return {"webcams": [{"index": c.pipeline.source.index, "available": True, "resolution": "in use"}], "note": "webcam in use"}
    from src.sources.webcam import probe_webcams
    return {"webcams": probe_webcams(max_index)}


@router.post("/source/upload")
async def upload_video(request: Request, file: UploadFile = File(...)):
    c = ctx(request)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported format '{suffix}'. Use MP4, AVI, MOV or MKV.")
    name = safe_filename(Path(file.filename or "upload").stem)[:40] + "_" + uuid.uuid4().hex[:6] + suffix
    dest = c.uploads_dir / name
    size = 0
    with dest.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > 2 * 1024 ** 3:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(400, "File too large (2 GB limit)")
            out.write(chunk)
    import cv2
    cap = cv2.VideoCapture(str(dest))
    ok = cap.isOpened()
    if ok:
        ok, _ = cap.read()
    cap.release()
    if not ok:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "Could not decode this video. Re-encode it as H.264 MP4 and try again.")
    return {"ok": True, "path": str(dest.relative_to(c.base_dir)), "name": name}


# ------------------------------------------------------------------ demo
@router.post("/demo/{action}")
def demo_action(action: str, request: Request, payload: DemoAction | None = None):
    c = ctx(request)
    p = c.pipeline
    payload = payload or DemoAction()
    try:
        if action == "webcam":
            return {"ok": True, "state": p.start({"type": "webcam", "index": payload.index or 0, "name": "Laptop Webcam"})}
        if action == "recorded":
            path = payload.path or c.cfg.demo.get("recorded_video") or ""
            if not path:
                assets = list_video_assets([c.demo_assets_dir, c.uploads_dir], c.base_dir)
                if not assets:
                    return {"ok": True, "state": p.start({"type": "synthetic", "name": "Synthetic Factory Floor"}),
                            "note": "No recorded video found in demo_assets/ — started the synthetic scene instead."}
                path = assets[0]["path"]
            name = "Recorded Factory Demo" if "vtest" not in path else "Recorded Demo (pedestrians)"
            return {"ok": True, "state": p.start({"type": "file", "path": path, "loop": True, "name": name})}
        if action == "synthetic":
            return {"ok": True, "state": p.start({"type": "synthetic", "name": "Synthetic Factory Floor"})}
        if action == "reset-counts":
            p.reset_counts()
            return {"ok": True}
        if action == "verify-dwell":
            secs = p.verify_dwell(payload.seconds)
            return {"ok": True, "threshold_seconds": secs,
                    "message": f"Dwell threshold is {secs:.0f}s for the next 2 minutes. Ask someone to stand inside the restricted zone."}
        if action == "test-event":
            ev = p.fire_test_event(payload.rule_type or "restricted_zone_intrusion")
            return {"ok": True, "event": event_view(ev, _tz(c))}
        if action == "enable-restricted":
            if not p.source_id:
                raise HTTPException(400, "Start a source first")
            zones = demo_layout_zones([z.to_dict() for z in p.zones])
            saved, problems = p.save_zones(p.source_id, zones)
            if problems:
                raise HTTPException(400, json.dumps(problems))
            return {"ok": True, "zones": saved}
        if action == "clear-zones":
            if not p.source_id:
                raise HTTPException(400, "Start a source first")
            saved, _ = p.save_zones(p.source_id, [])
            return {"ok": True, "zones": saved}
    except SourceError as exc:
        raise HTTPException(400, str(exc))
    raise HTTPException(404, f"Unknown demo action '{action}'")


# ------------------------------------------------------------------ zones
@router.get("/zones")
def get_zones(request: Request, source_id: Optional[str] = None):
    c = ctx(request)
    sid = source_id or c.pipeline.source_id
    zones = [z.to_dict() for z in c.pipeline.zones] if (sid == c.pipeline.source_id and sid) else \
        c.repos.zones.list_for_source(sid) if sid else []
    return {"source_id": sid, "zones": zones, "kinds": ZONE_KINDS, "presets": {"synthetic": default_synthetic_zones(),
            "demo_layout": demo_layout_zones([])}}


@router.put("/zones")
def put_zones(payload: ZonesSave, request: Request):
    c = ctx(request)
    sid = payload.source_id or c.pipeline.source_id
    if not sid:
        raise HTTPException(400, "Start a source first so zones can be saved against it")
    saved, problems = c.pipeline.save_zones(sid, payload.zones)
    if problems:
        raise HTTPException(422, {"message": "Zone validation failed", "problems": problems})
    return {"ok": True, "source_id": sid, "zones": saved}


# ------------------------------------------------------------------ rules / settings
@router.get("/rules")
def get_rules(request: Request):
    c = ctx(request)
    return {"rules": [r.to_dict() for r in c.pipeline.rules_engine.rules], "types": {t.value: RULE_TITLES[t] for t in RuleType},
            "business_hours": c.pipeline.settings["business_hours"]}


@router.put("/rules")
def put_rules(payload: RulesSave, request: Request):
    return {"ok": True, "rules": ctx(request).pipeline.update_rules(payload.rules)}


@router.get("/settings")
def get_settings(request: Request):
    c = ctx(request)
    s = dict(c.pipeline.settings)
    s["webhook"] = {**s.get("webhook", {}), "url": s.get("webhook", {}).get("url", "")}  # URL without secrets is fine
    return {"settings": s, "config": {"processing": c.cfg.processing.to_dict(), "model": {k: v for k, v in c.cfg.model.to_dict().items()},
                                      "tracking": c.cfg.tracking.to_dict(), "evidence": c.cfg.evidence.to_dict(),
                                      "analytics": c.cfg.analytics.to_dict()}}


@router.put("/settings")
def put_settings(payload: dict, request: Request):
    c = ctx(request)
    return {"ok": True, "settings": c.pipeline.apply_settings(payload)}


@router.post("/webhook/test")
def webhook_test(request: Request):
    c = ctx(request)
    if not c.webhook.url:
        raise HTTPException(400, "Configure a webhook URL first")
    payload = {"type": "souveno.vision.test", "sent_at": utc_iso(), "message": "Souveno Vision Intelligence webhook test"}
    return c.webhook.deliver(payload)


# ------------------------------------------------------------------ events
def _filters(date_from, date_to, source_id, event_type, severity, status, search) -> dict:
    f = {}
    if date_from:
        f["date_from"] = date_from if "T" in date_from else f"{date_from}T00:00:00Z"
    if date_to:
        f["date_to"] = date_to if "T" in date_to else f"{date_to}T23:59:59Z"
    for k, v in (("source_id", source_id), ("event_type", event_type), ("severity", severity), ("status", status), ("search", search)):
        if v:
            f[k] = v
    return f


@router.get("/events")
def list_events(request: Request, date_from: Optional[str] = None, date_to: Optional[str] = None, source_id: Optional[str] = None,
                event_type: Optional[str] = None, severity: Optional[str] = None, status: Optional[str] = None,
                search: Optional[str] = None, limit: int = 100, offset: int = 0):
    c = ctx(request)
    f = _filters(date_from, date_to, source_id, event_type, severity, status, search)
    repo = c.repos.events
    return {"events": [event_view(e, _tz(c)) for e in repo.list(f, limit, offset)], "total": repo.count(f), "filters": f,
            "options": {"event_type": [t.value for t in RuleType], "severity": ["low", "medium", "high", "critical"],
                        "status": ["new", "acknowledged", "resolved", "dismissed"],
                        "source_id": [{"id": s["source_id"], "name": s["name"]} for s in c.repos.sources.list()]}}


@router.get("/events/export.csv")
def export_events(request: Request, date_from: Optional[str] = None, date_to: Optional[str] = None, source_id: Optional[str] = None,
                  event_type: Optional[str] = None, severity: Optional[str] = None, status: Optional[str] = None,
                  search: Optional[str] = None):
    c = ctx(request)
    csv_text = c.events.export_csv(_filters(date_from, date_to, source_id, event_type, severity, status, search))
    name = f"souveno_events_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(content=csv_text, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={name}"})


@router.get("/events/{event_id}")
def get_event(event_id: str, request: Request):
    c = ctx(request)
    e = c.repos.events.get(event_id)
    if not e:
        raise HTTPException(404, "Event not found")
    v = event_view(e, _tz(c))
    v["audit"] = c.repos.acks.for_event(event_id)
    return v


@router.post("/events/{event_id}/{action}")
def event_action(event_id: str, action: str, request: Request, payload: EventAction | None = None):
    c = ctx(request)
    payload = payload or EventAction()
    fn = {"ack": c.events.acknowledge, "acknowledge": c.events.acknowledge, "resolve": c.events.resolve,
          "dismiss": c.events.dismiss, "reopen": c.events.reopen}.get(action)
    if not fn:
        raise HTTPException(404, f"Unknown action '{action}'")
    updated = fn(event_id, payload.actor or "operator", payload.note or "")
    if not updated:
        raise HTTPException(404, "Event not found")
    return {"ok": True, "event": event_view(updated, _tz(c))}


def _evidence_file(c, event_id: str, key: str) -> Path:
    e = c.repos.events.get(event_id)
    if not e or not e.get(key):
        raise HTTPException(404, "Evidence not available for this event")
    p = Path(e[key])
    try:
        p.resolve().relative_to(c.evidence.dir.resolve())  # only files inside the evidence folder are ever served
    except ValueError:
        raise HTTPException(403, "Evidence path outside the evidence directory")
    if not p.exists():
        raise HTTPException(404, "Evidence file has been removed (retention)")
    return p


@router.get("/events/{event_id}/snapshot")
def event_snapshot(event_id: str, request: Request):
    p = _evidence_file(ctx(request), event_id, "snapshot_path")
    return FileResponse(str(p), media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/events/{event_id}/clip")
def event_clip(event_id: str, request: Request):
    p = _evidence_file(ctx(request), event_id, "clip_path")
    media = "video/mp4" if p.suffix.lower() == ".mp4" else "video/x-msvideo"
    return FileResponse(str(p), media_type=media, filename=p.name)


# ------------------------------------------------------------------ audit
@router.post("/audit")
def start_audit(payload: AuditStart, request: Request):
    c = ctx(request)
    spec = {k: v for k, v in payload.spec.model_dump().items() if v is not None}
    audit_id = c.audits.start(spec, min(max(payload.duration_seconds, 3.0), 30.0))
    return {"ok": True, "audit_id": audit_id}


@router.get("/audit")
def list_audits(request: Request):
    return {"audits": ctx(request).audits.list()}


@router.get("/audit/{audit_id}")
def get_audit(audit_id: str, request: Request):
    r = ctx(request).audits.get(audit_id)
    if not r:
        raise HTTPException(404, "Audit not found")
    return r.to_dict()


# ------------------------------------------------------------------ websocket
@ws_router.websocket("/ws/vi/live")
async def live_ws(websocket: WebSocket):
    await websocket.accept()
    c = websocket.app.state.ctx
    last_ts = ""
    try:
        while True:
            st = c.pipeline.state()
            recent = [event_view(e, _tz(c)) for e in c.events.recent(30)]
            new = [e for e in recent if e["timestamp"] > last_ts] if last_ts else recent[:10]
            if recent:
                last_ts = max(last_ts, max(e["timestamp"] for e in recent))
            st["new_events"] = new
            st["recent_events"] = recent
            st["stats"] = c.events.stats_today()
            await websocket.send_text(json.dumps(st, default=str))
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # pragma: no cover
        logger.debug(f"live ws closed: {exc}")

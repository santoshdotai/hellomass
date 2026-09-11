"""FastAPI application factory for Souveno Vision Intelligence.

* `/`            new dashboard (src/ui/static)
* `/api/vi/*`    JSON + MJPEG API (src/ui/api.py)
* `/ws/vi/live`  state push
* `/cafe`        the original café demo, untouched (its own routers, /static, /api/sessions …)
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from loguru import logger

from src.events.evidence import EvidenceManager
from src.events.service import EventService
from src.events.webhook import WebhookDispatcher
from src.monitoring.camera_audit import AuditRunner
from src.monitoring.health import HealthMonitor
from src.monitoring.logging_config import setup_logging
from src.pipeline import VisionPipeline
from src.storage.database import Database
from src.storage.repositories import Repositories
from src.utils.config import BASE_DIR, Config, deep_merge, load_config, resolve_path

STATIC_DIR = Path(__file__).resolve().parent / "static"


class AppContext:
    """Everything the API needs, built once at startup."""

    def __init__(self, cfg: Config, base_dir: Path = BASE_DIR):
        self.cfg = cfg
        self.base_dir = base_dir
        self.log_path = setup_logging(cfg.logging.level, cfg.logging.directory, cfg.logging.rotation, cfg.logging.retention, base_dir)
        self.db = Database(resolve_path(cfg.database.path, base_dir)).connect()
        self.repos = Repositories(self.db)
        ev = cfg.evidence
        self.evidence = EvidenceManager(resolve_path(ev.directory, base_dir), ev.pre_event_seconds, ev.post_event_seconds,
                                        cfg.processing.analytics_fps, ev.clip_enabled, ev.max_concurrent_clips,
                                        ev.max_clips_per_minute, ev.retention_days, ev.max_storage_mb,
                                        cfg.processing.evidence_max_width)
        wh = cfg.webhook
        self.webhook = WebhookDispatcher(wh.enabled, wh.url or "", wh.timeout_seconds, wh.max_retries, wh.backoff_seconds,
                                         wh.get("auth_header_env", ""))
        self.events = EventService(self.repos, self.evidence, self.webhook)
        self.health = HealthMonitor(resolve_path("data", base_dir))
        self.pipeline = VisionPipeline(cfg, self.repos, self.events, self.evidence, self.health, self.webhook, base_dir)
        self.audits = AuditRunner(cfg.source.rtsp.to_dict(), base_dir)
        self.uploads_dir = resolve_path("data/uploads", base_dir)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.demo_assets_dir = resolve_path("demo_assets", base_dir)
        w = self.pipeline.settings.get("webhook", {})
        if w.get("enabled") and w.get("url"):
            self.webhook.configure(True, w["url"], w.get("timeout_seconds"), w.get("max_retries"), w.get("backoff_seconds"))
        self.health.set_component("database", self.db.status()["ok"], str(self.db.path))
        self.health.set_component("evidence", True, str(self.evidence.dir))
        logger.info(f"{cfg.app.name} initialised (db={self.db.path.name}, demo_mode={cfg.app.get('demo_mode', True)})")

    def shutdown(self) -> None:
        self.pipeline.shutdown()
        self.db.close()


def _mount_legacy(app: FastAPI) -> bool:
    """Keep the original café demo reachable at /cafe with all of its routes."""
    try:
        from backend.api.routers import analysis, cameras, config_router, cost, events as cafe_events, health as cafe_health, sessions, zones as cafe_zones
        from backend.db.database import init_db as cafe_init_db
        from config.settings import settings as cafe_settings
    except Exception as exc:  # legacy demo is optional
        logger.warning(f"Legacy café demo not mounted: {exc}")
        return False
    for r in (cafe_health.router, sessions.router, cafe_zones.router, analysis.router, analysis.ws_router, cafe_events.router,
              config_router.router, cost.router, cameras.router):
        app.include_router(r)
    frontend = cafe_settings.base_dir / "frontend"
    if frontend.exists():
        app.mount("/static", StaticFiles(directory=str(frontend)), name="cafe-static")

        @app.get("/cafe", include_in_schema=False)
        def cafe_index():
            return FileResponse(str(frontend / "index.html"))
    app.state.cafe_init_db = cafe_init_db
    return True


def create_app(cfg: Config | None = None, overrides: dict | None = None, base_dir: Path = BASE_DIR,
               mount_legacy: bool = True) -> FastAPI:
    cfg = cfg or load_config()
    if overrides:
        cfg = Config(deep_merge(cfg.to_dict(), overrides))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        ctx = AppContext(cfg, base_dir)
        app.state.ctx = ctx
        init_cafe = getattr(app.state, "cafe_init_db", None)
        if init_cafe:
            try:
                init_cafe()
            except Exception as exc:
                logger.warning(f"Legacy café database init failed: {exc}")
        if cfg.app.get("autostart_source"):
            try:
                ctx.pipeline.start(_source_spec_from_config(cfg))
            except Exception as exc:
                logger.warning(f"Autostart failed: {exc}")
        yield
        ctx.shutdown()

    app = FastAPI(title=cfg.app.name, description=cfg.app.tagline, lifespan=lifespan, docs_url="/api/docs", redoc_url=None)
    from src.ui.api import router, ws_router
    app.include_router(router)
    app.include_router(ws_router)
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR)), name="assets")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(str(STATIC_DIR / "index.html"))

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return Response(status_code=204)

    if mount_legacy:
        _mount_legacy(app)
    return app


def _source_spec_from_config(cfg: Config) -> dict:
    s = cfg.source
    kind = s.type
    spec = {"type": kind, "name": s.name}
    if kind == "webcam":
        spec["index"] = int(s.webcam_index)
    elif kind == "file":
        spec["path"] = s.video_path
        spec["loop"] = bool(s.loop)
    elif kind == "rtsp":
        spec["stream_profile"] = s.rtsp.stream_profile
        spec["transport"] = s.rtsp.transport
    return spec


app = None  # created lazily by app.py / tests via create_app()

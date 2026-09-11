"""SOUVENO VISION — FastAPI application entrypoint."""
from __future__ import annotations

import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from loguru import logger

from backend.api.routers import expo
from backend.db.database import init_db
from config.settings import settings

logger.remove()
logger.add(sys.stderr, level=settings.log_level)
try:
    logger.add(settings.logs_dir / "souveno_vision.log", rotation="10 MB", retention=5, level="DEBUG")
except OSError:  # read-only host (serverless)
    pass

EXPO_ONLY = settings.app_mode == "expo"
if not EXPO_ONLY:
    from backend.api.routers import analysis, cameras, config_router, cost, events, health, sessions, zones


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info(f"{settings.app_name} starting — demo_mode={settings.demo_mode}")
    yield
    logger.info(f"{settings.app_name} shutting down")


app = FastAPI(title=settings.app_name, description=settings.tagline, lifespan=lifespan)

if not EXPO_ONLY:
    app.include_router(health.router)
    app.include_router(sessions.router)
    app.include_router(zones.router)
    app.include_router(analysis.router)
    app.include_router(analysis.ws_router)
    app.include_router(events.router)
    app.include_router(config_router.router)
    app.include_router(cost.router)
    app.include_router(cameras.router)
else:
    @app.get("/api/health")
    def health_expo():
        return {"status": "ok", "app": settings.app_name, "mode": "expo", "database": settings.database_url.split("://")[0]}
app.include_router(expo.router)

FRONTEND_DIR = settings.base_dir / "frontend"
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
def index():
    if EXPO_ONLY:
        return FileResponse(str(FRONTEND_DIR / "expo.html"))
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.get("/expo")
def expo_dashboard():
    return FileResponse(str(FRONTEND_DIR / "expo.html"))


@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(str(FRONTEND_DIR / "manifest.webmanifest"), media_type="application/manifest+json")


@app.get("/sw.js")
def service_worker():
    return FileResponse(str(FRONTEND_DIR / "sw.js"), media_type="application/javascript", headers={"Service-Worker-Allowed": "/"})


@app.get("/expo/card")
def expo_card():
    """Public page behind the QR on Souveno's business card: visitors leave
    their details and get Souveno's contact card back."""
    return FileResponse(str(FRONTEND_DIR / "card.html"))

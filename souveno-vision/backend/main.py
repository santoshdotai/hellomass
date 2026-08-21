"""SOUVENO VISION — FastAPI application entrypoint."""
from __future__ import annotations

import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from loguru import logger

from backend.api.routers import analysis, cameras, config_router, cost, events, health, sessions, zones
from backend.db.database import init_db
from config.settings import settings

logger.remove()
logger.add(sys.stderr, level=settings.log_level)
logger.add(settings.logs_dir / "souveno_vision.log", rotation="10 MB", retention=5, level="DEBUG")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info(f"{settings.app_name} starting — demo_mode={settings.demo_mode}")
    yield
    logger.info(f"{settings.app_name} shutting down")


app = FastAPI(title=settings.app_name, description=settings.tagline, lifespan=lifespan)

app.include_router(health.router)
app.include_router(sessions.router)
app.include_router(zones.router)
app.include_router(analysis.router)
app.include_router(analysis.ws_router)
app.include_router(events.router)
app.include_router(config_router.router)
app.include_router(cost.router)
app.include_router(cameras.router)

FRONTEND_DIR = settings.base_dir / "frontend"
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))

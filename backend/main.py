"""Souveno Expo Agent — standalone FastAPI backend (no OpenCV / YOLO).

Serves the JSON API under /api/expo. The frontend is a separate static app
(expo-frontend); set EXPO_CORS_ORIGINS to its origin(s), or point
EXPO_FRONTEND_DIR at a checkout of it to have this process serve it too.
"""
from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from backend.api.routers import expo
from backend.db.database import init_db
from config.settings import settings

logger.remove()
logger.add(sys.stderr, level=settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Souveno Expo Agent API starting")
    yield


app = FastAPI(title="Souveno Expo Agent API", description="Exhibition agent for Souveno AI Solutions", lifespan=lifespan)
origins = [o.strip() for o in os.environ.get("EXPO_CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
app.include_router(expo.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": "souveno-expo-agent", "database": settings.database_url.split("://")[0]}


# Optional: serve the static frontend from the same process (combined deploy).
_fe = os.environ.get("EXPO_FRONTEND_DIR") or str(settings.base_dir.parent / "expo-frontend")
FRONTEND_DIR = Path(_fe)
if FRONTEND_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    @app.get("/expo")
    def index():
        return FileResponse(str(FRONTEND_DIR / "index.html"))

    @app.get("/expo/card")
    def card():
        return FileResponse(str(FRONTEND_DIR / "card.html"))

    @app.get("/manifest.webmanifest")
    def manifest():
        return FileResponse(str(FRONTEND_DIR / "manifest.webmanifest"), media_type="application/manifest+json")

    @app.get("/sw.js")
    def service_worker():
        return FileResponse(str(FRONTEND_DIR / "sw.js"), media_type="application/javascript", headers={"Service-Worker-Allowed": "/"})

    # index.html references its assets relatively (config.js, css/, js/, icons, dashboard/);
    # serve those from the frontend folder too so the combined deploy works at "/".
    _ASSET_TOP = {"config.js", "card.html", "icon.svg", "icon-maskable.svg"}

    @app.get("/{asset:path}", include_in_schema=False)
    def frontend_asset(asset: str):
        top = asset.split("/", 1)[0]
        if asset in _ASSET_TOP or top in ("css", "js", "dashboard"):
            target = (FRONTEND_DIR / asset).resolve()
            if str(target).startswith(str(FRONTEND_DIR.resolve())) and target.is_file():
                return FileResponse(str(target))
        raise HTTPException(404, "not found")
else:
    @app.get("/")
    def root():
        return {"app": "souveno-expo-agent", "docs": "/docs", "api": "/api/expo/events", "frontend": "deploy expo-frontend separately and set EXPO_CORS_ORIGINS"}

from fastapi import APIRouter

from backend.core.detector import resolve_device
from config.settings import settings

router = APIRouter(tags=["health"])


@router.get("/api/health")
def health():
    return {
        "status": "ok",
        "app": settings.app_name,
        "tagline": settings.tagline,
        "demo_mode": settings.demo_mode,
        "inference_device": "NVIDIA GPU" if resolve_device() == "cuda" else "CPU",
    }

#!/usr/bin/env python3
"""SOUVENO VISION — single-command launcher.

Usage:
    python run.py
"""
import uvicorn

from config.settings import settings

if __name__ == "__main__":
    print(f"\n{settings.app_name}\n{settings.tagline}\n")
    print(f"Starting server at http://{settings.host}:{settings.port}  (demo_mode={settings.demo_mode})\n")
    uvicorn.run("backend.main:app", host=settings.host, port=settings.port, reload=False)

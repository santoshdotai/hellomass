#!/usr/bin/env python3
"""Souveno Vision Intelligence — single-command launcher.

    python app.py                      # dashboard at http://127.0.0.1:8501
    python app.py --source webcam      # start the laptop webcam immediately
    python app.py --source file --path demo_assets/clip.mp4
    python app.py --source rtsp        # URL/credentials from .env (SOUVENO_RTSP_*)
    python app.py --port 9000 --host 0.0.0.0

Stop with Ctrl+C: the capture thread, clip writers and database are closed cleanly.
"""
from __future__ import annotations

import argparse
import os
import sys
import webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.chdir(BASE_DIR)


def main() -> None:
    parser = argparse.ArgumentParser(description="Souveno Vision Intelligence")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--source", choices=["webcam", "file", "rtsp", "synthetic"], default=None,
                        help="start this source immediately")
    parser.add_argument("--path", default=None, help="video file path for --source file")
    parser.add_argument("--webcam-index", type=int, default=None)
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default=None)
    parser.add_argument("--no-browser", action="store_true", help="do not open the dashboard in a browser")
    parser.add_argument("--no-legacy", action="store_true", help="do not mount the legacy café demo at /cafe")
    args = parser.parse_args()

    overrides: dict = {"app": {}, "source": {}, "model": {}}
    if args.host:
        overrides["app"]["host"] = args.host
    if args.port:
        overrides["app"]["port"] = args.port
    if args.source:
        overrides["source"]["type"] = args.source
        overrides["app"]["autostart_source"] = True
    if args.path:
        overrides["source"]["video_path"] = args.path
    if args.webcam_index is not None:
        overrides["source"]["webcam_index"] = args.webcam_index
    if args.device:
        overrides["model"]["device"] = args.device

    import uvicorn
    from src.ui.dashboard import create_app
    from src.utils.config import load_config

    cfg = load_config()
    app = create_app(cfg, overrides, BASE_DIR, mount_legacy=not args.no_legacy)
    host = args.host or cfg.app.host
    port = args.port or int(cfg.app.port)
    url = f"http://{'127.0.0.1' if host in ('0.0.0.0', '') else host}:{port}"
    print(f"\n  SOUVENO AI — {cfg.app.name}\n  {cfg.app.tagline}\n\n  Dashboard: {url}\n  Health:    {url}/#health\n  Stop with Ctrl+C\n")
    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()

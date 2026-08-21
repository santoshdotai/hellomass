#!/usr/bin/env python3
"""Download the vision models SOUVENO VISION needs (Phase 2).

Run: python scripts/download_models.py [--pose] [--seg] [--all]

Ultralytics downloads weights automatically the first time a model is
loaded, so this script mainly exists to (a) pre-warm the cache before a
live demo so there's no first-request delay, and (b) place the files
under models/<kind>/ so config/model_config.py's layout matches disk.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.model_config import get_model_path  # noqa: E402
from config.settings import settings  # noqa: E402


def download(kind: str, filename: str):
    from ultralytics import YOLO
    target = get_model_path(kind, filename)
    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {filename} -> {target}")
    YOLO(str(target))  # triggers download to `target` if missing, else loads it
    print(f"  OK ({target.stat().st_size / 1e6:.1f} MB)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pose", action="store_true", help="Also download the pose model")
    parser.add_argument("--seg", action="store_true", help="Also download the segmentation model")
    parser.add_argument("--all", action="store_true", help="Download detection + pose + segmentation")
    args = parser.parse_args()

    download("detection", settings.detection_model)
    if args.pose or args.all:
        download("pose", settings.pose_model)
    if args.seg or args.all:
        download("segmentation", settings.segmentation_model)

    print("\nModel download complete.")


if __name__ == "__main__":
    main()

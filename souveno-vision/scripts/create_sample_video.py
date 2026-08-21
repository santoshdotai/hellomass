#!/usr/bin/env python3
"""Fetch a small test video with real people in it, so the pipeline can be
exercised end-to-end without requiring you to already have café footage.

We deliberately do NOT synthesize fake "people" out of drawn shapes —
YOLO is trained on real photos and would (correctly) detect nothing in a
video of colored rectangles, which would make for a dishonest test. Instead
this downloads OpenCV's own long-standing pedestrian test clip (`vtest.avi`,
BSD-3 licensed, part of the OpenCV project, used in countless detection
tutorials) — real people walking, safe to redistribute, small (~8MB).

This is a generic walking-pedestrians clip, not café footage — it is only
here to prove the detection/tracking/zone/event pipeline works. For a real
demo, upload your own recorded café video instead.

Run: python scripts/create_sample_video.py
"""
import sys
from pathlib import Path
from urllib.request import urlretrieve

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import settings  # noqa: E402

SAMPLE_URL = "https://raw.githubusercontent.com/opencv/opencv/master/samples/data/vtest.avi"


def main():
    out_dir = settings.data_dir / "sample_videos"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "sample_pedestrians.avi"

    if out_path.exists():
        print(f"Sample video already present: {out_path}")
        return

    print(f"Downloading sample test video from {SAMPLE_URL} ...")
    urlretrieve(SAMPLE_URL, out_path)
    print(f"Saved to {out_path} ({out_path.stat().st_size / 1e6:.1f} MB)")
    print("\nUpload this file from the SOUVENO VISION home screen to test the full pipeline, "
          "or drop your own café MP4 in for a real demo.")


if __name__ == "__main__":
    main()

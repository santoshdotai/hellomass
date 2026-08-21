#!/usr/bin/env python3
"""Wipe all demo data — sessions, zones, events, alerts, metrics, summaries
— and start from a clean database (Phase 24 'reset all data'). Uploaded
video files and generated clips/screenshots on disk are left untouched
unless --purge-files is passed.

Run: python scripts/reset_demo.py [--purge-files]
"""
import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.db.database import Base, engine, init_db  # noqa: E402
from config.settings import settings  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--purge-files", action="store_true",
                         help="Also delete uploaded videos, clips, and screenshots")
    args = parser.parse_args()

    print("Dropping and recreating all tables...")
    Base.metadata.drop_all(bind=engine)
    init_db()
    print("Database reset complete.")

    if args.purge_files:
        for d in [settings.uploads_dir, settings.clips_dir, settings.screenshots_dir]:
            for f in Path(d).glob("*"):
                if f.is_file():
                    f.unlink()
            print(f"Purged files in {d}")

    print("\nSOUVENO VISION demo data reset.")


if __name__ == "__main__":
    main()

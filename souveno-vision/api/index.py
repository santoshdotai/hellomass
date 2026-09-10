"""Vercel Python entrypoint: serves the Expo Agent in expo-only mode.
Set APP_MODE=expo and DATABASE_URL (Supabase Postgres) in the Vercel project."""
import os
import sys
from pathlib import Path

os.environ.setdefault("APP_MODE", "expo")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.main import app  # noqa: E402,F401

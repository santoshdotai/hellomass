"""Vercel Python entrypoint for the Souveno Expo Agent (expo-only mode).

Two ways to run:
  * repo files present next to this file (git-linked deploy)  -> import directly
  * bootstrap deploy (only api/, requirements.txt, vercel.json uploaded) ->
    download the public GitHub branch tarball into /tmp once per instance,
    then import the app from there. Set SOUVENO_SOURCE_REF to pin a branch/tag.

Env: APP_MODE=expo (default here), DATABASE_URL (Supabase Postgres; without it
SQLite lives in /tmp and resets on cold start).
"""
import io
import os
import sys
import tarfile
import urllib.request
from pathlib import Path

os.environ.setdefault("APP_MODE", "expo")
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

REPO = os.environ.get("SOUVENO_SOURCE_REPO", "santoshdotai/hellomass")
REF = os.environ.get("SOUVENO_SOURCE_REF", "expo-backend")
SUBDIR = os.environ.get("SOUVENO_SOURCE_SUBDIR", "")  # "" on the expo-backend branch (app at repo root); "expo-backend" on the monorepo branch
FE_REF = os.environ.get("SOUVENO_FRONTEND_REF", "expo-frontend")  # the web app is served from "/" too (same deployment)
FE_SUBDIR = os.environ.get("SOUVENO_FRONTEND_SUBDIR", "")


def _bootstrap(ref: str = REF, subdir: str = SUBDIR, marker_rel: str = "backend/main.py") -> Path:
    cache = Path("/tmp/souveno-src") / ref.replace("/", "_")
    root = cache / subdir if subdir else cache
    if (root / marker_rel).exists():
        return root
    cache.mkdir(parents=True, exist_ok=True)
    url = f"https://codeload.github.com/{REPO}/tar.gz/refs/heads/{ref}"
    with urllib.request.urlopen(url, timeout=40) as r:
        data = r.read()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        members = tf.getmembers()
        top = members[0].name.split("/")[0]
        for m in members:
            rel = m.name[len(top) + 1:]
            if subdir and not rel.startswith(subdir + "/"):
                continue
            if not rel:
                continue
            m.name = rel
            tf.extract(m, cache)
    return root


if (ROOT / "backend" / "main.py").exists():
    SRC = ROOT
else:
    SRC = _bootstrap()
sys.path.insert(0, str(SRC))
os.chdir(SRC)

# Serve the web app from the same deployment: local folder if present, else the expo-frontend branch.
if not os.environ.get("EXPO_FRONTEND_DIR"):
    local_fe = ROOT.parent / "expo-frontend"
    if (local_fe / "index.html").exists():
        os.environ["EXPO_FRONTEND_DIR"] = str(local_fe)
    else:
        try:
            os.environ["EXPO_FRONTEND_DIR"] = str(_bootstrap(FE_REF, FE_SUBDIR, "index.html"))
        except Exception:  # noqa: BLE001 - API still works without the web app
            pass

from backend.main import app  # noqa: E402,F401

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
REF = os.environ.get("SOUVENO_SOURCE_REF", "claude/nice-pasteur-omkzao")
SUBDIR = os.environ.get("SOUVENO_SOURCE_SUBDIR", "souveno-vision")


def _bootstrap() -> Path:
    cache = Path("/tmp/souveno-src") / REF.replace("/", "_")
    marker = cache / SUBDIR / "backend" / "main.py"
    if marker.exists():
        return cache / SUBDIR
    cache.mkdir(parents=True, exist_ok=True)
    url = f"https://codeload.github.com/{REPO}/tar.gz/refs/heads/{REF}"
    with urllib.request.urlopen(url, timeout=40) as r:
        data = r.read()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        members = tf.getmembers()
        top = members[0].name.split("/")[0]
        for m in members:
            rel = m.name[len(top) + 1:]
            if not rel.startswith(SUBDIR + "/"):
                continue
            m.name = rel
            tf.extract(m, cache)
    return cache / SUBDIR


if (ROOT / "backend" / "main.py").exists():
    SRC = ROOT
else:
    SRC = _bootstrap()
sys.path.insert(0, str(SRC))
os.chdir(SRC)

from backend.main import app  # noqa: E402,F401

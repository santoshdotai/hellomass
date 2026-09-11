"""Server-side presentation helpers shared by the API and pages (no business logic)."""
from __future__ import annotations

from pathlib import Path

from src.sources.video_file import SUPPORTED_EXTENSIONS
from src.utils.time_utils import local_display, parse_iso

SEVERITY_COLORS = {"low": "#8c8c8c", "medium": "#faad14", "high": "#fa541c", "critical": "#f5222d"}
SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def event_view(e: dict, tz_name: str = "local") -> dict:
    """Add display fields + evidence URLs to a stored event dict (paths never exposed)."""
    v = dict(e)
    try:
        v["time_local"] = local_display(parse_iso(e["timestamp"]), tz_name)
    except Exception:
        v["time_local"] = e.get("timestamp", "")
    v["severity_color"] = SEVERITY_COLORS.get(e.get("severity", "low"), "#8c8c8c")
    v["severity_rank"] = SEVERITY_RANK.get(e.get("severity", "low"), 0)
    v["snapshot_url"] = f"/api/vi/events/{e['event_id']}/snapshot" if e.get("snapshot_path") else None
    v["clip_url"] = f"/api/vi/events/{e['event_id']}/clip" if e.get("clip_path") else None
    v["has_snapshot"] = bool(e.get("snapshot_path"))
    v["has_clip"] = bool(e.get("clip_path"))
    v.pop("snapshot_path", None)
    v.pop("clip_path", None)
    return v


def list_video_assets(dirs: list[Path], base_dir: Path) -> list[dict]:
    out = []
    for d in dirs:
        if not d.exists():
            continue
        for f in sorted(d.iterdir()):
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
                try:
                    rel = str(f.relative_to(base_dir))
                except ValueError:
                    rel = str(f)
                out.append({"name": f.name, "path": rel, "size_mb": round(f.stat().st_size / 1e6, 1), "folder": d.name})
    return out


def demo_layout_zones(existing: list[dict]) -> list[dict]:
    """Add a restricted zone + a virtual line + an occupancy zone if the layout lacks them (webcam demo)."""
    kinds = {z.get("kind") for z in existing}
    zones = [dict(z) for z in existing]
    if "restricted" not in kinds:
        zones.append({"name": "Restricted Area", "kind": "restricted", "points": [[0.62, 0.12], [0.97, 0.12], [0.97, 0.95], [0.62, 0.95]],
                      "color": "#ff4d4f"})
    if "line" not in kinds:
        zones.append({"name": "Entry Line", "kind": "line", "points": [[0.40, 0.08], [0.40, 0.95]], "color": "#ffd666",
                      "in_label": "Entry", "out_label": "Exit"})
    if "occupancy" not in kinds:
        zones.append({"name": "Work Area", "kind": "occupancy", "points": [[0.03, 0.12], [0.38, 0.12], [0.38, 0.95], [0.03, 0.95]],
                      "color": "#36cfc9", "occupancy_limit": 3})
    return zones


PRIVACY_STATEMENT = ("This demonstration uses anonymous, camera-local tracking IDs. It does not identify employees.")

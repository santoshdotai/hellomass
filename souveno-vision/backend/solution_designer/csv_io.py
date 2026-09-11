"""CSV import/export for the camera inventory.

The column set is the CameraSpec field list so a client can fill the
template in a spreadsheet. Booleans accept yes/no/true/false/1/0/y/n;
blank cells mean "unknown", never "no".
"""
from __future__ import annotations

import csv
import io

from pydantic import ValidationError

from backend.solution_designer.schemas import CameraSpec

CSV_COLUMNS = [
    "ref", "name", "count", "area", "make_model", "camera_type", "resolution", "fps", "bitrate_mbps", "codec",
    "rtsp_available", "onvif_available", "mainstream_available", "substream_available", "is_ptz", "view_type",
    "lighting", "occlusion", "motion_blur", "stream_stability", "subject_distance_m", "subject_height_px",
    "use_cases", "notes",
]
BOOL_COLUMNS = {"rtsp_available", "onvif_available", "mainstream_available", "substream_available", "is_ptz"}
NUM_COLUMNS = {"count": int, "fps": float, "bitrate_mbps": float, "subject_distance_m": float, "subject_height_px": int}

TRUE = {"yes", "y", "true", "1"}
FALSE = {"no", "n", "false", "0"}


def _parse_bool(v: str):
    s = (v or "").strip().lower()
    if s == "" or s in ("unknown", "?", "na", "n/a"):
        return None
    if s in TRUE:
        return True
    if s in FALSE:
        return False
    raise ValueError(f"cannot interpret '{v}' as yes/no/unknown")


def parse_csv(content: str) -> tuple[list[CameraSpec], list[dict]]:
    """Returns (valid cameras, row errors). Never raises on a bad row."""
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        return [], [{"row": 0, "error": "Empty CSV"}]
    missing = [c for c in ("name",) if c not in reader.fieldnames]
    if missing:
        return [], [{"row": 0, "error": f"Missing required column(s): {missing}"}]
    cameras: list[CameraSpec] = []
    errors: list[dict] = []
    for i, row in enumerate(reader, start=2):
        data: dict = {}
        try:
            for col in CSV_COLUMNS:
                raw = (row.get(col) or "").strip()
                if raw == "":
                    continue
                if col in BOOL_COLUMNS:
                    data[col] = _parse_bool(raw)
                elif col in NUM_COLUMNS:
                    data[col] = NUM_COLUMNS[col](float(raw)) if NUM_COLUMNS[col] is int else float(raw)
                elif col == "use_cases":
                    data[col] = [u.strip() for u in raw.replace(";", ",").split(",") if u.strip()]
                else:
                    data[col] = raw
            cameras.append(CameraSpec(**data))
        except (ValidationError, ValueError) as e:
            errors.append({"row": i, "name": row.get("name"), "error": str(e).splitlines()[0][:300]})
    return cameras, errors


def to_csv(cameras: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    w.writeheader()
    for c in cameras:
        row = dict(c)
        for b in BOOL_COLUMNS:
            v = row.get(b)
            row[b] = "" if v is None else ("yes" if v else "no")
        if isinstance(row.get("use_cases"), list):
            row["use_cases"] = ";".join(row["use_cases"])
        w.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in CSV_COLUMNS})
    return buf.getvalue()


def template_csv() -> str:
    return to_csv([{
        "ref": "CAM-GRP-01", "name": "Dispatch dock domes", "count": 12, "area": "Dispatch", "make_model": "Hikvision DS-2CD2143",
        "camera_type": "ip_fixed", "resolution": "1080p", "fps": 15, "bitrate_mbps": 4, "codec": "h264",
        "rtsp_available": True, "onvif_available": True, "mainstream_available": True, "substream_available": True,
        "is_ptz": False, "view_type": "oblique", "lighting": "good", "occlusion": "partial", "motion_blur": "some",
        "stream_stability": "stable", "subject_distance_m": 8, "subject_height_px": 120,
        "use_cases": ["restricted_zone", "ppe"], "notes": "leave blank cells for unknown values",
    }])

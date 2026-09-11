"""Static reference data for the Solution Designer.

Use-case catalogue, codec compatibility, GPU reference table and the
constants used by the scoring engine. Everything here is data; nothing
here calls an LLM.
"""
from __future__ import annotations

SITE_VALIDATION = "Site validation required"

CODECS = {
    "h264": {"label": "H.264 / AVC", "decoder_support": "universal", "score": 1.0,
              "note": "Universally hardware-decodable; preferred for analytics."},
    "h265": {"label": "H.265 / HEVC", "decoder_support": "modern", "score": 0.85,
              "note": "Lower bandwidth; needs an HEVC-capable decoder (most GPUs from 2016 onward)."},
    "mjpeg": {"label": "MJPEG", "decoder_support": "cpu", "score": 0.5,
               "note": "Very high bandwidth and CPU-decoded; usable for a few streams only."},
    "mpeg4": {"label": "MPEG-4 Part 2", "decoder_support": "legacy", "score": 0.4,
               "note": "Legacy codec, usually from old DVR/analog paths; often software-decoded."},
    "proprietary": {"label": "Proprietary", "decoder_support": "none", "score": 0.1,
                     "note": "Proprietary encodings cannot be consumed without a vendor SDK."},
}

RESOLUTIONS = {
    # key: (width, height, megapixels, score 0..1)
    "4k": (3840, 2160, 8.3, 1.0),
    "5mp": (2592, 1944, 5.0, 1.0),
    "4mp": (2560, 1440, 3.7, 1.0),
    "1080p": (1920, 1080, 2.1, 1.0),
    "720p": (1280, 720, 0.9, 0.7),
    "d1": (720, 576, 0.4, 0.3),
    "cif": (352, 288, 0.1, 0.1),
}

CAMERA_TYPES = {
    "ip_fixed": {"label": "IP fixed (bullet/dome)", "stream_path": "direct_or_nvr"},
    "ip_ptz": {"label": "IP PTZ", "stream_path": "direct_or_nvr"},
    "ip_fisheye": {"label": "IP fisheye / 360°", "stream_path": "direct_or_nvr"},
    "analog_dvr": {"label": "Analog / HD-TVI / CVI via DVR", "stream_path": "dvr_only"},
    "usb": {"label": "USB / webcam", "stream_path": "host_only"},
    "unknown": {"label": "Unknown", "stream_path": "unknown"},
}

# --------------------------------------------------------------- use cases
# view: overhead | eye_level | oblique | any ; subject_px: minimum subject
# height in pixels for reliable detection (used by the suitability engine).
USE_CASES: dict[str, dict] = {
    "people_counting": {
        "name": "People counting",
        "required_view": "Overhead or high-mounted oblique view of a doorway or corridor with a clear crossing line.",
        "view_types": ["overhead", "oblique"],
        "suggested_resolution": "1080p",
        "analytics_fps": 8,
        "min_subject_px": 60,
        "placement": "Camera above the entrance, looking down at 45–90°, no glass reflections, counting line fully inside the frame.",
        "model_category": "Person detection + multi-object tracking (anonymous IDs)",
        "business_rule": "Count entries/exits when a tracked person crosses the virtual line in each direction.",
        "alert_workflow": "No real-time alert; hourly/daily counts to dashboard and optional threshold alert.",
        "evidence": "Aggregate counts only; optional 5-second clip on threshold breach.",
        "limitations": "Crowds walking shoulder-to-shoulder, umbrellas, trolleys and revolving doors reduce accuracy. Not identity-aware.",
        "success_metric": "≥ 95% agreement with manual ground-truth count over 3 validation windows.",
        "privacy_level": "anonymous",
    },
    "occupancy": {
        "name": "Occupancy",
        "required_view": "Wide view covering the whole area (room, floor, waiting area) with minimal blind spots.",
        "view_types": ["overhead", "oblique", "eye_level"],
        "suggested_resolution": "1080p",
        "analytics_fps": 5,
        "min_subject_px": 50,
        "placement": "Corner-mounted at 3–4 m height; full area coverage; avoid partial views that require guessing.",
        "model_category": "Person detection + zone counting",
        "business_rule": "Alert when the number of people inside a defined zone exceeds a configurable limit for longer than N seconds.",
        "alert_workflow": "Dashboard tile with live occupancy; alert to floor supervisor on threshold breach.",
        "evidence": "Snapshot at breach time; occupancy time-series stored.",
        "limitations": "Occlusion in dense areas under-counts; large areas may need multiple cameras with de-duplication.",
        "success_metric": "Occupancy within ±10% of manual spot checks in 90% of samples.",
        "privacy_level": "anonymous",
    },
    "line_crossing": {
        "name": "Line crossing",
        "required_view": "Clear view perpendicular to the line being monitored.",
        "view_types": ["overhead", "oblique"],
        "suggested_resolution": "1080p",
        "analytics_fps": 10,
        "min_subject_px": 60,
        "placement": "Line must be fully visible; camera not looking along the line; stable mount.",
        "model_category": "Person/vehicle detection + tracking + direction logic",
        "business_rule": "Trigger when a tracked object crosses the line in the configured direction.",
        "alert_workflow": "Instant alert (< configured latency) to security console; optional siren integration via relay.",
        "evidence": "Snapshot + 10-second clip around the crossing.",
        "limitations": "Fast movement at low FPS can skip the line; reflections and shadows can cause false triggers at night.",
        "success_metric": "≥ 95% true-positive rate and ≤ 2 false alerts per camera per day in the pilot.",
        "privacy_level": "anonymous",
    },
    "restricted_zone": {
        "name": "Restricted-zone detection",
        "required_view": "Full view of the restricted area boundary and its approaches.",
        "view_types": ["overhead", "oblique", "eye_level"],
        "suggested_resolution": "1080p",
        "analytics_fps": 8,
        "min_subject_px": 60,
        "limitations": "Cannot distinguish authorised from unauthorised staff without a separately approved identification module; schedule/role-based rules are used instead.",
        "placement": "Zone boundary fully in frame; avoid views where the zone is partially hidden by machinery.",
        "model_category": "Person detection + polygon-zone intrusion logic",
        "business_rule": "Alert when a person is inside the zone outside allowed hours or for longer than the grace period.",
        "alert_workflow": "Instant alert to control room and area owner; escalate if not acknowledged in N minutes.",
        "evidence": "Snapshot + 15-second clip; entry/exit timestamps.",
        "success_metric": "≥ 95% detection of staged intrusions; ≤ 1 false alert per camera per day.",
        "privacy_level": "anonymous",
    },
    "loitering": {
        "name": "Loitering / dwell time",
        "required_view": "Stable view of the area with the subject visible for the whole dwell period.",
        "view_types": ["oblique", "eye_level", "overhead"],
        "suggested_resolution": "1080p",
        "analytics_fps": 5,
        "min_subject_px": 50,
        "placement": "Avoid views where people are routinely occluded (pillars, vehicles) because track loss resets dwell timers.",
        "model_category": "Person detection + long-term tracking",
        "business_rule": "Alert when a tracked person remains in the zone longer than the configured dwell threshold.",
        "alert_workflow": "Alert to security after threshold; auto-close when the person leaves.",
        "evidence": "Snapshot at threshold; time-lapse clip of the dwell.",
        "limitations": "Track ID switches on occlusion inflate or reset dwell; not reliable in dense crowds.",
        "success_metric": "≥ 90% of staged loitering events detected within threshold + 30 s.",
        "privacy_level": "anonymous",
    },
    "after_hours": {
        "name": "After-hours movement",
        "required_view": "Any view of the protected area with adequate night illumination or IR.",
        "view_types": ["any"],
        "suggested_resolution": "720p",
        "analytics_fps": 5,
        "min_subject_px": 40,
        "placement": "Ensure IR illuminators cover the area; avoid pointing at moving trees, fans or reflective surfaces.",
        "model_category": "Person/vehicle detection with schedule gating",
        "business_rule": "Alert on any person/vehicle detection during the configured closed hours.",
        "alert_workflow": "Instant alert to security and WhatsApp/SMS to the site owner.",
        "evidence": "Snapshot + 20-second clip.",
        "limitations": "Insects, animals and IR reflections create false alerts at night; pure motion detection is not used.",
        "success_metric": "≥ 95% staged-intrusion detection; ≤ 1 false alert per camera per night.",
        "privacy_level": "anonymous",
    },
    "ppe": {
        "name": "PPE detection",
        "required_view": "Eye-level or slightly elevated view where helmets, vests, gloves or masks are visible at ≥ 100 px subject height.",
        "view_types": ["eye_level", "oblique"],
        "suggested_resolution": "1080p or higher",
        "analytics_fps": 5,
        "min_subject_px": 100,
        "placement": "Camera at 2.5–3.5 m facing the direction workers approach; avoid backlighting and overhead-only views.",
        "model_category": "Person detection + PPE attribute classification (site-specific fine-tuning usually required)",
        "business_rule": "Flag a person without the required PPE inside a PPE-mandatory zone for longer than N seconds.",
        "alert_workflow": "Alert to shift supervisor; daily compliance report by zone.",
        "evidence": "Snapshot with detection boxes; compliance percentage by shift.",
        "limitations": "Small or partially hidden PPE (gloves, ear plugs) is unreliable; helmet and vest are the dependable classes; requires site-specific validation.",
        "success_metric": "≥ 90% helmet/vest compliance classification agreement with human review on a 200-sample audit.",
        "privacy_level": "anonymous_but_hr_sensitive",
    },
    "person_down": {
        "name": "Person-down / fall detection",
        "required_view": "Oblique view where the full body is visible on the floor; not overhead-only.",
        "view_types": ["oblique", "eye_level"],
        "suggested_resolution": "1080p",
        "analytics_fps": 10,
        "min_subject_px": 80,
        "placement": "Unobstructed floor view; avoid areas where people routinely sit, kneel or lie down as part of work.",
        "model_category": "Person detection + pose estimation + temporal rule",
        "business_rule": "Alert when a person's posture is horizontal near floor level for longer than N seconds.",
        "alert_workflow": "Highest-priority alert to first-aid responder and control room.",
        "evidence": "Snapshot + 20-second clip.",
        "limitations": "Kneeling, bending and lying-down work postures cause false alerts; heavy occlusion hides real falls. Never the sole safety mechanism.",
        "success_metric": "≥ 90% staged-fall detection within 15 s; false alerts tolerated by the client's safety team.",
        "privacy_level": "anonymous",
    },
    "vehicle_proximity": {
        "name": "Vehicle / pedestrian proximity",
        "required_view": "High oblique view covering the shared vehicle-pedestrian area with both classes visible.",
        "view_types": ["overhead", "oblique"],
        "suggested_resolution": "1080p",
        "analytics_fps": 10,
        "min_subject_px": 60,
        "placement": "Mount high enough that vehicles do not fully hide pedestrians; avoid perspective where distance is ambiguous.",
        "model_category": "Person + vehicle detection + tracking + distance estimation",
        "business_rule": "Alert when a pedestrian and a moving vehicle are within the configured pixel/ground distance.",
        "alert_workflow": "Instant alert to forklift operator (audible) and safety officer.",
        "evidence": "Snapshot + 10-second clip.",
        "limitations": "Distance is estimated in image space unless the floor plane is calibrated; not a certified safety system.",
        "success_metric": "≥ 90% staged near-miss detection; near-miss frequency trend available per zone.",
        "privacy_level": "anonymous",
    },
    "queue_monitoring": {
        "name": "Queue monitoring",
        "required_view": "View along or across the queue with each person separable.",
        "view_types": ["oblique", "overhead"],
        "suggested_resolution": "1080p",
        "analytics_fps": 5,
        "min_subject_px": 50,
        "placement": "Camera facing the queue at an angle so people do not fully occlude one another.",
        "model_category": "Person detection + zone counting + dwell",
        "business_rule": "Alert when queue length or average wait exceeds thresholds.",
        "alert_workflow": "Alert to floor manager to open another counter.",
        "evidence": "Queue length time-series; snapshot on breach.",
        "limitations": "Dense queues under-count; people standing near but not in the queue can be miscounted.",
        "success_metric": "Queue length within ±1 person of manual count in 90% of samples.",
        "privacy_level": "anonymous",
    },
    "camera_tampering": {
        "name": "Camera tampering",
        "required_view": "Any fixed view.",
        "view_types": ["any"],
        "suggested_resolution": "any",
        "analytics_fps": 2,
        "min_subject_px": 0,
        "placement": "No placement change required; baseline scene is learned automatically.",
        "model_category": "Scene-change / obstruction / defocus detection (no person model)",
        "business_rule": "Alert when the scene is covered, moved, defocused or the stream drops for longer than N seconds.",
        "alert_workflow": "Alert to security and IT; ticket to maintenance.",
        "evidence": "Before/after snapshots.",
        "limitations": "Lighting changes and PTZ movement can trigger false alerts; PTZ cameras are excluded unless parked.",
        "success_metric": "100% of staged tamper events detected within 60 s; ≤ 1 false alert per camera per week.",
        "privacy_level": "none",
    },
}

# Reference decoder capability. `benchmark_available` is False everywhere
# until Souveno has measured a representative workload on that GPU. This is
# deliberate: the engine must never derive a camera count from VRAM or from
# vendor marketing figures.
GPU_CATALOG: dict[str, dict] = {
    "t4": {"name": "NVIDIA T4", "vram_gb": 16, "nvdec_engines": 1, "hevc": True, "class": "datacenter_entry", "benchmark_available": False},
    "a2": {"name": "NVIDIA A2", "vram_gb": 16, "nvdec_engines": 1, "hevc": True, "class": "datacenter_entry", "benchmark_available": False},
    "a10": {"name": "NVIDIA A10", "vram_gb": 24, "nvdec_engines": 2, "hevc": True, "class": "datacenter_mid", "benchmark_available": False},
    "a16": {"name": "NVIDIA A16", "vram_gb": 64, "nvdec_engines": 8, "hevc": True, "class": "datacenter_decode", "benchmark_available": False},
    "l4": {"name": "NVIDIA L4", "vram_gb": 24, "nvdec_engines": 2, "hevc": True, "class": "datacenter_mid", "benchmark_available": False},
    "l40s": {"name": "NVIDIA L40S", "vram_gb": 48, "nvdec_engines": 3, "hevc": True, "class": "datacenter_high", "benchmark_available": False},
    "a100": {"name": "NVIDIA A100", "vram_gb": 40, "nvdec_engines": 5, "hevc": True, "class": "datacenter_high", "benchmark_available": False},
    "rtx3060": {"name": "NVIDIA GeForce RTX 3060", "vram_gb": 12, "nvdec_engines": 1, "hevc": True, "class": "consumer", "benchmark_available": False},
    "rtx4060": {"name": "NVIDIA GeForce RTX 4060", "vram_gb": 8, "nvdec_engines": 1, "hevc": True, "class": "consumer", "benchmark_available": False},
    "rtx4070": {"name": "NVIDIA GeForce RTX 4070", "vram_gb": 12, "nvdec_engines": 1, "hevc": True, "class": "consumer", "benchmark_available": False},
    "rtx4090": {"name": "NVIDIA GeForce RTX 4090", "vram_gb": 24, "nvdec_engines": 2, "hevc": True, "class": "consumer_high", "benchmark_available": False},
    "rtxa4000": {"name": "NVIDIA RTX A4000", "vram_gb": 16, "nvdec_engines": 1, "hevc": True, "class": "workstation", "benchmark_available": False},
    "jetson_orin_nx": {"name": "NVIDIA Jetson Orin NX", "vram_gb": 16, "nvdec_engines": 1, "hevc": True, "class": "edge", "benchmark_available": False},
    "jetson_agx_orin": {"name": "NVIDIA Jetson AGX Orin", "vram_gb": 64, "nvdec_engines": 2, "hevc": True, "class": "edge", "benchmark_available": False},
}

GPU_ALIASES = {
    "tesla t4": "t4", "t4": "t4", "a2": "a2", "a10": "a10", "a10g": "a10", "a16": "a16", "l4": "l4",
    "l40s": "l40s", "a100": "a100", "rtx 3060": "rtx3060", "rtx3060": "rtx3060",
    "rtx 4060": "rtx4060", "rtx4060": "rtx4060", "rtx 4070": "rtx4070", "rtx4070": "rtx4070",
    "rtx 4090": "rtx4090", "rtx4090": "rtx4090", "rtx a4000": "rtxa4000", "a4000": "rtxa4000",
    "orin nx": "jetson_orin_nx", "agx orin": "jetson_agx_orin",
}

GPU_CAPACITY_DISCLAIMER = (
    "Final GPU capacity cannot be guaranteed without benchmarking representative client streams."
)

MODEL_SIZES = {
    "nano": {"label": "Nano (e.g. YOLO11n)", "relative_cost": 1.0},
    "small": {"label": "Small (e.g. YOLO11s)", "relative_cost": 2.2},
    "medium": {"label": "Medium (e.g. YOLO11m)", "relative_cost": 5.5},
    "large": {"label": "Large (e.g. YOLO11l)", "relative_cost": 9.0},
}


def normalise_gpu_name(raw: str | None) -> str | None:
    """Map a free-text GPU name (from a form or nvidia-smi) onto a catalogue key."""
    if not raw:
        return None
    text = raw.lower().replace("nvidia", "").replace("geforce", "").replace("tesla", "").strip()
    text = " ".join(text.split())
    if text in GPU_CATALOG:
        return text
    for alias, key in sorted(GPU_ALIASES.items(), key=lambda kv: -len(kv[0])):
        if alias in text:
            return key
    return None


def use_case_ids() -> list[str]:
    return list(USE_CASES.keys())

"""Camera suitability engine.

Scores each camera (or camera group) from 0–100 across twelve factors and
classifies it A/B/C/D. Every factor returns the points awarded, the reason,
and whether the input was missing — missing inputs are never guessed; they
are scored conservatively and flagged "Site validation required".

Hard blockers (no obtainable stream) force class D regardless of score.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from backend.solution_designer.catalog import CODECS, RESOLUTIONS, SITE_VALIDATION, USE_CASES

# Maximum points per factor (sums to 100).
WEIGHTS = {
    "stream_accessibility": 20,
    "resolution": 12,
    "subject_size": 12,
    "camera_angle": 8,
    "lighting": 8,
    "occlusion": 6,
    "motion_blur": 6,
    "stream_stability": 8,
    "fps": 6,
    "codec": 6,
    "mount": 4,
    "use_case_fit": 4,
}
assert sum(WEIGHTS.values()) == 100

CLASS_LABELS = {
    "A": "AI ready",
    "B": "Usable after configuration",
    "C": "Basic analytics only",
    "D": "Unsuitable",
}


@dataclass
class FactorResult:
    factor: str
    points: float
    max_points: int
    reason: str
    validation_required: bool = False
    action: str | None = None  # what the client must change, if anything

    def as_dict(self) -> dict:
        return {
            "factor": self.factor, "points": round(self.points, 1), "max_points": self.max_points,
            "reason": self.reason, "validation_required": self.validation_required, "action": self.action,
        }


@dataclass
class SuitabilityResult:
    camera_ref: str
    label: str
    count: int
    score: int
    classification: str
    class_label: str
    hard_blockers: list[str]
    factors: list[FactorResult]
    validation_items: list[str]
    required_actions: list[str]
    use_case_notes: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "camera_ref": self.camera_ref, "label": self.label, "count": self.count,
            "score": self.score, "classification": self.classification, "class_label": self.class_label,
            "hard_blockers": self.hard_blockers, "factors": [f.as_dict() for f in self.factors],
            "validation_items": self.validation_items, "required_actions": self.required_actions,
            "use_case_notes": self.use_case_notes,
        }


def _unknown(factor: str, fraction: float = 0.35, what: str = "") -> FactorResult:
    w = WEIGHTS[factor]
    return FactorResult(factor, w * fraction, w,
                        f"{what or factor.replace('_', ' ').capitalize()} not provided. {SITE_VALIDATION}.",
                        validation_required=True)


# ---------------------------------------------------------------- factors
def score_stream_accessibility(cam: dict, nvr: dict | None) -> tuple[FactorResult, str | None]:
    """Returns (factor, hard_blocker_or_None)."""
    w = WEIGHTS["stream_accessibility"]
    ctype = cam.get("camera_type") or "unknown"
    rtsp = cam.get("rtsp_available")
    onvif = cam.get("onvif_available")
    substream = cam.get("substream_available")
    nvr_rtsp = (nvr or {}).get("rtsp_available")
    nvr_api = (nvr or {}).get("api_sdk_available")

    if ctype == "analog_dvr":
        if nvr_rtsp is True or nvr_api is True:
            return FactorResult("stream_accessibility", w * 0.55, w,
                                "Analog camera; stream is only obtainable through the DVR's RTSP/API output. "
                                "DVR re-encoding quality and channel limits must be validated on site.",
                                validation_required=True,
                                action="Confirm DVR exposes per-channel RTSP and its outbound stream limit."), None
        if nvr_rtsp is False and nvr_api is False:
            return FactorResult("stream_accessibility", 0, w,
                                "Analog camera behind a DVR that exposes neither RTSP nor an API — no usable video stream exists.",
                                action="Replace the DVR with an RTSP-capable recorder or add an encoder/new IP camera."), \
                "No obtainable video stream (analog camera, DVR without RTSP/API)"
        return FactorResult("stream_accessibility", w * 0.25, w,
                            f"Analog camera via DVR; DVR RTSP/API capability unknown. {SITE_VALIDATION}.",
                            validation_required=True,
                            action="Verify whether the DVR can output RTSP per channel."), None

    if ctype == "usb":
        return FactorResult("stream_accessibility", w * 0.2, w,
                            "USB camera — only reachable from the host it is plugged into; not a network stream.",
                            action="Replace with an IP camera for production."), None

    if rtsp is True:
        pts = w * (1.0 if onvif or substream else 0.9)
        detail = " ONVIF/substream available." if (onvif or substream) else " Confirm substream availability to reduce decode load."
        return FactorResult("stream_accessibility", pts, w, "Direct RTSP stream confirmed." + detail,
                            validation_required=not (onvif or substream)), None

    if rtsp is False:
        if nvr_rtsp is True or nvr_api is True:
            return FactorResult("stream_accessibility", w * 0.7, w,
                                "Camera has no direct RTSP, but the NVR/VMS can re-stream it. Subject to the NVR's "
                                "outbound-stream limit.", validation_required=True,
                                action="Validate NVR outbound stream count and latency."), None
        if nvr_rtsp is False and nvr_api is False:
            return FactorResult("stream_accessibility", 0, w,
                                "No direct RTSP and the NVR exposes neither RTSP nor an API — no usable stream.",
                                action="Enable RTSP on the camera, or obtain NVR SDK access, or replace the NVR."), \
                "No obtainable video stream (no camera RTSP, NVR without RTSP/API)"
        return FactorResult("stream_accessibility", w * 0.3, w,
                            f"No direct RTSP; NVR re-streaming capability unknown. {SITE_VALIDATION}.",
                            validation_required=True, action="Check NVR RTSP/API capability."), None

    # rtsp unknown
    if nvr_rtsp is True or nvr_api is True:
        return FactorResult("stream_accessibility", w * 0.6, w,
                            f"Camera RTSP status unknown; NVR can re-stream. {SITE_VALIDATION} for the camera itself.",
                            validation_required=True), None
    return FactorResult("stream_accessibility", w * 0.35, w,
                        f"Stream accessibility unknown (an IP address alone does not prove a usable stream). {SITE_VALIDATION}.",
                        validation_required=True, action="Test RTSP/ONVIF access on site."), None


def score_resolution(cam: dict) -> FactorResult:
    w = WEIGHTS["resolution"]
    res = cam.get("resolution")
    if not res:
        return _unknown("resolution", 0.35, "Resolution")
    key = str(res).lower()
    if key in RESOLUTIONS:
        _, _, mp, s = RESOLUTIONS[key]
        reason = f"{key.upper()} (~{mp} MP)."
        action = None
        if s < 0.5:
            reason += " Below the 720p minimum for person-level analytics."
            action = "Upgrade to a ≥1080p camera for anything beyond basic motion/tamper analytics."
        elif s < 1.0:
            reason += " Adequate for counting/occupancy; marginal for PPE."
        return FactorResult("resolution", w * s, w, reason, action=action)
    return FactorResult("resolution", w * 0.35, w, f"Unrecognised resolution '{res}'. {SITE_VALIDATION}.", True)


def score_subject_size(cam: dict, use_cases: list[str]) -> FactorResult:
    w = WEIGHTS["subject_size"]
    px = cam.get("subject_height_px")
    dist = cam.get("subject_distance_m")
    if px is None and dist is None:
        return _unknown("subject_size", 0.35, "Effective subject size (distance or subject pixel height)")
    needed = max([USE_CASES[u]["min_subject_px"] for u in use_cases if u in USE_CASES] or [60])
    if needed == 0:
        return FactorResult("subject_size", w, w, "Selected use cases do not depend on subject size.")
    if px is None:
        # Distance only: coarse banding. Not a substitute for a measurement.
        if dist <= 8:
            return FactorResult("subject_size", w * 0.8, w,
                                f"Subjects within {dist} m — likely adequate; pixel size not measured. {SITE_VALIDATION}.", True)
        if dist <= 15:
            return FactorResult("subject_size", w * 0.55, w,
                                f"Subjects at ~{dist} m — marginal for attribute analytics such as PPE. {SITE_VALIDATION}.", True)
        return FactorResult("subject_size", w * 0.2, w,
                            f"Subjects at ~{dist} m — too far for reliable person-level analytics at typical resolutions.",
                            action="Reposition the camera closer or add a camera for the target zone.")
    ratio = px / needed
    if ratio >= 1.5:
        return FactorResult("subject_size", w, w, f"Subject height ~{px} px vs {needed} px required.")
    if ratio >= 1.0:
        return FactorResult("subject_size", w * 0.8, w, f"Subject height ~{px} px meets the {needed} px minimum.")
    if ratio >= 0.6:
        return FactorResult("subject_size", w * 0.4, w,
                            f"Subject height ~{px} px is below the {needed} px minimum for the selected use cases.",
                            action="Reposition, zoom, or use a higher-resolution camera for this view.")
    return FactorResult("subject_size", w * 0.1, w,
                        f"Subject height ~{px} px is far below the {needed} px minimum.",
                        action="New camera placement required for this use case.")


def score_camera_angle(cam: dict, use_cases: list[str]) -> FactorResult:
    w = WEIGHTS["camera_angle"]
    view = cam.get("view_type")
    if not view:
        return _unknown("camera_angle", 0.4, "Camera angle / view type")
    wanted = set()
    for u in use_cases:
        wanted.update(USE_CASES.get(u, {}).get("view_types", []))
    if "any" in wanted or not wanted or view in wanted:
        return FactorResult("camera_angle", w, w, f"{view.replace('_', ' ').capitalize()} view suits the selected use cases.")
    if view == "overhead" and ("eye_level" in wanted or "oblique" in wanted):
        return FactorResult("camera_angle", w * 0.3, w,
                            "Overhead view: people are seen from above, so PPE/fall/posture analytics are unreliable.",
                            action="Add an oblique/eye-level camera for attribute-based use cases.")
    return FactorResult("camera_angle", w * 0.5, w,
                        f"{view.replace('_', ' ').capitalize()} view is workable but not ideal for every selected use case.")


def score_lighting(cam: dict) -> FactorResult:
    w = WEIGHTS["lighting"]
    l = cam.get("lighting")
    table = {
        "good": (1.0, "Consistent lighting.", None),
        "variable": (0.6, "Variable lighting (doors, windows, shifts); expect accuracy to vary by time of day.", None),
        "low": (0.3, "Low light without IR — detections degrade sharply.", "Add lighting or an IR-capable camera."),
        "ir_night": (0.7, "IR night mode: monochrome, adequate for detection, unreliable for colour-based PPE.", None),
        "backlit": (0.35, "Backlit view — subjects appear as silhouettes.", "Reposition camera or enable WDR."),
    }
    if not l:
        return _unknown("lighting", 0.4, "Lighting conditions")
    s, reason, action = table.get(l, (0.4, f"Unrecognised lighting '{l}'.", None))
    return FactorResult("lighting", w * s, w, reason, validation_required=(l not in table), action=action)


def score_occlusion(cam: dict) -> FactorResult:
    w = WEIGHTS["occlusion"]
    o = cam.get("occlusion")
    table = {"none": (1.0, "Clear view."), "partial": (0.55, "Partial occlusion (racks, pillars, vehicles) — track breaks expected."),
             "heavy": (0.15, "Heavily occluded view.")}
    if not o:
        return _unknown("occlusion", 0.4, "Occlusion")
    s, reason = table.get(o, (0.4, f"Unrecognised occlusion '{o}'."))
    return FactorResult("occlusion", w * s, w, reason, validation_required=(o not in table),
                        action="Reposition the camera or add a second angle." if o == "heavy" else None)


def score_motion_blur(cam: dict) -> FactorResult:
    w = WEIGHTS["motion_blur"]
    blur = cam.get("motion_blur")
    fps = cam.get("fps")
    if blur:
        table = {"none": (1.0, "No visible motion blur."), "some": (0.55, "Some motion blur on fast movement."),
                 "severe": (0.1, "Severe motion blur — long exposure or slow sensor.")}
        s, reason = table.get(blur, (0.4, f"Unrecognised motion blur '{blur}'."))
        return FactorResult("motion_blur", w * s, w, reason,
                            action="Reduce exposure time / improve lighting." if blur == "severe" else None)
    if fps:
        # FPS is a weak proxy: low FPS cameras usually run long exposures.
        s = 0.6 if fps >= 12 else 0.4
        return FactorResult("motion_blur", w * s, w,
                            f"Motion blur not assessed; inferred conservatively from {fps} FPS. {SITE_VALIDATION}.", True)
    return _unknown("motion_blur", 0.35, "Motion blur")


def score_stream_stability(cam: dict) -> FactorResult:
    w = WEIGHTS["stream_stability"]
    st = cam.get("stream_stability")
    table = {"stable": (1.0, "Stream reported stable."), "occasional_drops": (0.5, "Occasional stream drops reported."),
             "frequent_drops": (0.1, "Frequent drops — unusable for continuous analytics until fixed.")}
    if not st:
        return _unknown("stream_stability", 0.35, "Stream stability (needs a 24–72 h capture test)")
    s, reason = table.get(st, (0.35, f"Unrecognised stability '{st}'."))
    return FactorResult("stream_stability", w * s, w, reason,
                        action="Fix network/camera before pilot." if st == "frequent_drops" else None)


def score_fps(cam: dict, use_cases: list[str]) -> FactorResult:
    w = WEIGHTS["fps"]
    fps = cam.get("fps")
    if fps is None:
        return _unknown("fps", 0.4, "FPS")
    needed = max([USE_CASES[u]["analytics_fps"] for u in use_cases if u in USE_CASES] or [5])
    if fps >= max(needed, 12):
        return FactorResult("fps", w, w, f"{fps} FPS ≥ {needed} FPS required by the selected use cases.")
    if fps >= needed:
        return FactorResult("fps", w * 0.8, w, f"{fps} FPS meets the {needed} FPS analytics rate; little headroom.")
    return FactorResult("fps", w * 0.3, w, f"{fps} FPS is below the {needed} FPS analytics rate.",
                        action=f"Raise camera/NVR stream FPS to at least {needed}.")


def score_codec(cam: dict) -> FactorResult:
    w = WEIGHTS["codec"]
    c = (cam.get("codec") or "").lower()
    if not c:
        return _unknown("codec", 0.4, "Codec")
    if c in CODECS:
        info = CODECS[c]
        return FactorResult("codec", w * info["score"], w, f"{info['label']}: {info['note']}",
                            action="Switch stream to H.264/H.265." if info["score"] < 0.5 else None)
    return FactorResult("codec", w * 0.2, w, f"Unrecognised codec '{c}'. {SITE_VALIDATION}.", True)


def score_mount(cam: dict) -> FactorResult:
    w = WEIGHTS["mount"]
    ctype = cam.get("camera_type")
    ptz = cam.get("is_ptz")
    if ptz is None and ctype:
        ptz = ctype == "ip_ptz"
    if ptz is None:
        return _unknown("mount", 0.5, "Fixed/PTZ status")
    if ptz:
        return FactorResult("mount", w * 0.2, w,
                            "PTZ camera — zones and lines are only valid while parked at one preset.",
                            action="Lock a home preset for analytics or use a fixed camera.")
    return FactorResult("mount", w, w, "Fixed camera.")


def score_use_case_fit(cam: dict, use_cases: list[str]) -> tuple[FactorResult, dict]:
    w = WEIGHTS["use_case_fit"]
    notes = {}
    if not use_cases:
        return FactorResult("use_case_fit", w * 0.5, w, "No use case selected for this camera."), notes
    fits = 0
    for u in use_cases:
        uc = USE_CASES.get(u)
        if not uc:
            continue
        ok = True
        why = []
        if cam.get("is_ptz") or cam.get("camera_type") == "ip_ptz":
            if u == "camera_tampering":
                ok = False; why.append("PTZ excluded from tamper detection unless parked")
        view = cam.get("view_type")
        if view and "any" not in uc["view_types"] and view not in uc["view_types"]:
            ok = False; why.append(f"{view} view not suited to {uc['name'].lower()}")
        px = cam.get("subject_height_px")
        if px is not None and px < uc["min_subject_px"]:
            ok = False; why.append(f"subject {px}px < {uc['min_subject_px']}px needed")
        notes[u] = {"fit": ok, "reasons": why or ["No conflict found in provided data."]}
        fits += 1 if ok else 0
    frac = fits / max(len(use_cases), 1)
    return FactorResult("use_case_fit", w * frac, w,
                        f"{fits} of {len(use_cases)} selected use cases fit the provided camera data."), notes


# ---------------------------------------------------------------- scoring
def score_camera(cam: dict, nvr: dict | None, use_cases: list[str]) -> SuitabilityResult:
    """`cam` is a plain dict of camera/group fields (see schemas.CameraSpec)."""
    factors: list[FactorResult] = []
    blockers: list[str] = []

    f, blocker = score_stream_accessibility(cam, nvr)
    factors.append(f)
    if blocker:
        blockers.append(blocker)
    factors.append(score_resolution(cam))
    factors.append(score_subject_size(cam, use_cases))
    factors.append(score_camera_angle(cam, use_cases))
    factors.append(score_lighting(cam))
    factors.append(score_occlusion(cam))
    factors.append(score_motion_blur(cam))
    factors.append(score_stream_stability(cam))
    factors.append(score_fps(cam, use_cases))
    factors.append(score_codec(cam))
    factors.append(score_mount(cam))
    f, notes = score_use_case_fit(cam, use_cases)
    factors.append(f)

    score = int(round(sum(x.points for x in factors)))
    score = max(0, min(100, score))
    validation_items = [x.reason for x in factors if x.validation_required]
    actions = [x.action for x in factors if x.action]

    stream_factor = factors[0]
    if blockers:
        cls = "D"
    elif score >= 80:
        cls = "A"
    elif score >= 60:
        cls = "B"
    elif score >= 40:
        cls = "C"
    else:
        cls = "D"
    # Never award "AI ready" when the stream itself is unverified.
    if cls == "A" and stream_factor.validation_required:
        cls = "B"
        validation_items.append("Class capped at B until stream access is verified on site.")

    return SuitabilityResult(
        camera_ref=cam.get("ref") or cam.get("name") or "camera",
        label=cam.get("name") or cam.get("ref") or "camera",
        count=int(cam.get("count") or 1),
        score=score,
        classification=cls,
        class_label=CLASS_LABELS[cls],
        hard_blockers=blockers,
        factors=factors,
        validation_items=validation_items,
        required_actions=actions,
        use_case_notes=notes,
    )


def summarise(results: list[SuitabilityResult]) -> dict:
    counts = {k: 0 for k in CLASS_LABELS}
    units = {k: 0 for k in CLASS_LABELS}
    for r in results:
        counts[r.classification] += r.count
        units[r.classification] += 1
    total = sum(counts.values())
    return {
        "total_cameras": total,
        "by_class": {k: {"label": CLASS_LABELS[k], "cameras": counts[k], "entries": units[k]} for k in CLASS_LABELS},
        "candidate_ai_cameras": counts["A"] + counts["B"],
        "validation_required_cameras": sum(r.count for r in results if r.validation_items),
    }

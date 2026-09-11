"""Pilot designer: selects representative cameras, areas and use cases and
defines what the 30-day pilot must measure before any scale-up decision."""
from __future__ import annotations

from backend.solution_designer.catalog import USE_CASES
from backend.solution_designer.suitability import SuitabilityResult

USE_CASE_VALUE_ORDER = [
    # Highest business value / lowest technical risk first.
    "restricted_zone", "after_hours", "people_counting", "occupancy", "ppe", "line_crossing",
    "vehicle_proximity", "queue_monitoring", "loitering", "person_down", "camera_tampering",
]


def design_pilot(suitability: list[SuitabilityResult], cameras: list[dict], use_cases: list[str],
                 min_cameras: int = 8, max_cameras: int = 12, duration_days: int = 30,
                 pilot_max_cameras_commercial: int = 10) -> dict:
    # --- use cases: 2–3 highest value from the client's selection
    ranked = sorted(use_cases, key=lambda u: USE_CASE_VALUE_ORDER.index(u) if u in USE_CASE_VALUE_ORDER else 99)
    pilot_use_cases = ranked[:3] if len(ranked) >= 3 else ranked[:2] if len(ranked) >= 2 else ranked

    # --- areas: two distinct areas, preferring those with class A/B cameras
    by_ref = {c.get("ref") or c.get("name"): c for c in cameras}
    area_scores: dict[str, list[SuitabilityResult]] = {}
    for r in suitability:
        cam = by_ref.get(r.camera_ref, {})
        area = cam.get("area") or "Unassigned area"
        area_scores.setdefault(area, []).append(r)
    ranked_areas = sorted(area_scores.items(),
                          key=lambda kv: (-sum(x.count for x in kv[1] if x.classification in "AB"), kv[0]))
    pilot_areas = [a for a, _ in ranked_areas[:2]]

    # --- cameras: representative — spread across areas and groups, prefer A then B,
    # include one C if present so the pilot measures the "difficult" case too.
    selected: list[dict] = []
    target = min(max_cameras, max(min_cameras, pilot_max_cameras_commercial))

    def take(result: SuitabilityResult, n: int, why: str):
        nonlocal selected
        n = min(n, result.count, target - len(selected))
        for i in range(n):
            selected.append({
                "group": result.label,
                "area": by_ref.get(result.camera_ref, {}).get("area") or "Unassigned area",
                "classification": result.classification,
                "score": result.score,
                "reason": why,
                "unit": f"{result.label} #{i + 1}",
            })

    for cls, why in (("A", "AI-ready — measures achievable accuracy"),
                     ("B", "Usable after configuration — measures the configuration effort")):
        for area in pilot_areas:
            for r in sorted(area_scores.get(area, []), key=lambda x: -x.score):
                if r.classification == cls and len(selected) < target:
                    take(r, max(1, min(3, target // max(len(pilot_areas) * 2, 1))), why)
    for r in sorted(suitability, key=lambda x: -x.score):
        if r.classification == "C" and len(selected) < target:
            take(r, 1, "Basic-analytics camera included to measure the lower bound")
            break
    if len(selected) < min_cameras:
        for r in sorted(suitability, key=lambda x: -x.score):
            if r.classification in "AB" and len(selected) < min_cameras:
                take(r, min_cameras - len(selected), "Filled to reach the minimum representative sample")

    warnings = []
    if len(selected) < min_cameras:
        warnings.append(f"Only {len(selected)} camera(s) qualify for a pilot with the data provided; "
                        "site validation must find more usable cameras before the pilot starts.")
    if len(selected) > pilot_max_cameras_commercial:
        warnings.append(f"Pilot includes {len(selected)} cameras; the standard pilot fee covers up to "
                        f"{pilot_max_cameras_commercial}. Extra cameras are quoted separately.")

    return {
        "duration_days": duration_days,
        "cameras": selected,
        "camera_count": len(selected),
        "areas": pilot_areas,
        "use_cases": [{"id": u, "name": USE_CASES[u]["name"], "success_metric": USE_CASES[u]["success_metric"]}
                      for u in pilot_use_cases if u in USE_CASES],
        "validation_plan": {
            "ground_truth": "Manual counts and staged events on at least 3 dates per use case, recorded by client staff with timestamps.",
            "accuracy_measurement": "Precision/recall per use case against ground truth; target per success metric.",
            "false_positive_measurement": "False alerts per camera per day, reviewed daily with the client owner.",
            "stream_stability_measurement": "Stream uptime, reconnects and dropped-frame rate per camera over the full pilot.",
            "gpu_utilization_measurement": "GPU compute and decoder utilisation, VRAM and end-to-end latency per stream at pilot load and at a synthetic 2× load.",
            "network_utilization_measurement": "Per-camera substream bitrate and uplink utilisation at peak.",
        },
        "scale_up_decision_criteria": [
            "Each pilot use case meets its success metric on ground-truth days.",
            "False alerts per camera per day within the client-agreed tolerance for two consecutive weeks.",
            "Stream uptime ≥ 99% for pilot cameras with a known cause for every outage.",
            "GPU benchmark yields a measured streams-per-GPU figure for each stream profile — this figure sizes production hardware.",
            "Network utilisation stays below 70% of the recommended capacity at peak.",
            "HR/legal approvals in place for any use case involving identifiable staff evidence.",
        ],
        "warnings": warnings,
    }

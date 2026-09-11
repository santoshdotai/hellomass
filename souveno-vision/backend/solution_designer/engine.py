"""Assessment orchestrator: validated input → complete, traceable result dict."""
from __future__ import annotations

from datetime import datetime

from backend.solution_designer import calculators, compute as compute_mod, pilot as pilot_mod, pricing
from backend.solution_designer import recommendations as rec, suitability as suit
from backend.solution_designer.catalog import SITE_VALIDATION
from backend.solution_designer.narrative import build_narrative
from backend.solution_designer.schemas import AssessmentRequest, CameraSpec


def _expand_cameras(req: AssessmentRequest) -> list[dict]:
    """Camera dicts for the engines. If the client only gave a total count
    with no inventory, a single 'unspecified' group is created so the
    engine scores it honestly (everything unknown → validation required)."""
    cams = [c.model_dump() for c in req.cameras]
    declared = req.site.existing_camera_count
    inventory = sum(c["count"] for c in cams)
    if declared and declared > inventory:
        cams.append(CameraSpec(ref="UNSPECIFIED", name="Cameras with no specification provided",
                               count=declared - inventory, camera_type="unknown").model_dump())
    for i, c in enumerate(cams):
        c["ref"] = c.get("ref") or f"CAM-{i + 1:03d}"
        if not c.get("use_cases"):
            c["use_cases"] = list(req.requirements.use_cases)
    return cams


def _average_bitrate(cams: list[dict], assumed: float | None) -> tuple[float | None, str, list[str]]:
    """Weighted average of known bitrates; falls back to the configured
    assumption for unknown cameras and says so."""
    notes = []
    known = [(c["bitrate_mbps"], c["count"]) for c in cams if c.get("bitrate_mbps")]
    unknown_n = sum(c["count"] for c in cams if not c.get("bitrate_mbps"))
    if known and unknown_n == 0:
        total = sum(b * n for b, n in known) / sum(n for _, n in known)
        return round(total, 2), "measured", notes
    if assumed is None and not known:
        notes.append(f"No bitrate provided for any camera and no assumption configured. {SITE_VALIDATION}.")
        return None, "unknown", notes
    if assumed is None:
        # Extend known average to unknowns, flagged.
        avg_known = sum(b * n for b, n in known) / sum(n for _, n in known)
        notes.append(f"{unknown_n} camera(s) have unknown bitrate; the known-camera average ({avg_known:.2f} Mbps) was applied to them. {SITE_VALIDATION}.")
        return round(avg_known, 2), "extrapolated", notes
    total_n = sum(c["count"] for c in cams)
    weighted = (sum(b * n for b, n in known) + assumed * unknown_n) / total_n
    notes.append(f"{unknown_n} camera(s) have unknown bitrate; assumed {assumed} Mbps each. {SITE_VALIDATION}.")
    return round(weighted, 2), "assumed", notes


def run_assessment(req: AssessmentRequest) -> dict:
    cams = _expand_cameras(req)
    nvr = req.nvr.model_dump() if req.nvr else None
    server = req.server.model_dump() if req.server else None
    network = req.network.model_dump() if req.network else None
    reqs = req.requirements
    st = req.settings

    # 1. suitability
    results = [suit.score_camera(c, nvr, c["use_cases"]) for c in cams]
    summary = suit.summarise(results)

    # 2. deterministic calculations — analytics streams = class A + B cameras
    active = summary["candidate_ai_cameras"]
    avg_bitrate, source, bitrate_notes = _average_bitrate(cams, st.assumed_bitrate_mbps)
    calcs = calculators.run_all(
        active_stream_count=active, average_stream_bitrate_mbps=avg_bitrate, bitrate_source=source,
        safety_factor=st.network_safety_factor, analytics_fps=st.analytics_fps,
        events_per_day=reqs.events_per_camera_per_day, average_clip_size_mb=reqs.average_clip_size_mb,
        retention_days=reqs.evidence_retention_days, camera_count=active,
    )
    calcs["total_stream_bandwidth_mbps"]["assumptions"].extend(bitrate_notes)
    calcs["total_stream_bandwidth_mbps"]["assumptions"].append(
        f"Active stream count = class A + class B cameras ({active}); class C/D cameras are excluded until remediated.")
    # Full-inventory scenario, for comparison only.
    all_bw = calculators.total_stream_bandwidth(summary["total_cameras"], avg_bitrate, source)
    calcs["scenario_all_cameras_bandwidth_mbps"] = all_bw.as_dict()
    calcs["scenario_all_cameras_bandwidth_mbps"]["name"] = "scenario_all_cameras_bandwidth_mbps"
    calcs["scenario_all_cameras_bandwidth_mbps"]["assumptions"].append("Scenario only: every camera in the inventory streamed, regardless of class.")

    # 3. compute
    ab_cams = [c for c, r in zip(cams, results) if r.classification in "AB"]
    comp = compute_mod.assess_compute(server, ab_cams, reqs.use_cases, st.analytics_fps, st.model_size,
                                      tracking=True, required_alert_latency_s=reqs.required_alert_latency_s)

    # 4. use cases, architecture, pilot, risks, actions
    use_cases = rec.use_case_recommendations(reqs.use_cases, results)
    cloud_allowed = (network or {}).get("cloud_allowed")
    arch = rec.stream_architecture(nvr, network, cams, summary, cloud_allowed)
    pricing_cfg = pricing.validate_pricing(req.pricing_overrides or {})
    pil = pilot_mod.design_pilot(results, cams, reqs.use_cases, pilot_max_cameras_commercial=pricing_cfg["pilot_max_cameras"])
    privacy = {"employee_identification_requested": reqs.employee_identification_requested,
               "privacy_requirements": reqs.privacy_requirements}
    risks = rec.risk_register(cams, nvr, server, network, reqs.use_cases, results, comp, calcs, privacy)
    actions = rec.required_client_actions(results, nvr, server, network, reqs.use_cases, privacy)

    # 5. commercial (candidate cameras) + full-inventory scenario
    est = pricing.commercial_estimate(active, pricing_cfg, include_pilot=req.include_pilot_in_estimate)
    est_all = pricing.tiered_monthly_licence(summary["total_cameras"], pricing_cfg["licence_tiers"])

    decision = {
        "recommendation": "TECHNICAL PILOT FIRST",
        "final_hardware_recommended": False,
        "reason": ("Stream access, GPU capacity and detection accuracy are unproven for this site. Production hardware "
                   "and the final camera count will be specified only after the pilot benchmarks."),
    }
    if comp["benchmark_available"] and summary["validation_required_cameras"] == 0 and comp["gpu_status"] == "known":
        decision = {"recommendation": "PILOT WITH BENCHMARK CONFIRMATION", "final_hardware_recommended": False,
                    "reason": "Reference benchmarks exist but must be confirmed on the client's own streams."}

    assessment = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "module": "Souveno Vision Solution Designer",
        "input": req.model_dump(),
        "cameras_expanded": cams,
        "suitability": [r.as_dict() for r in results],
        "suitability_summary": summary,
        "calculations": calcs,
        "compute": comp,
        "use_cases": use_cases,
        "architecture": arch,
        "pilot": pil,
        "risks": risks,
        "required_client_actions": actions,
        "commercial": est,
        "commercial_scenario_all_cameras": est_all,
        "decision": decision,
        "assumptions": _collect_assumptions(calcs, comp, st, source),
        "safety_rules_applied": SAFETY_RULES,
    }
    narrative, generated_by = build_narrative(assessment)
    assessment["narrative"] = narrative
    assessment["narrative_generated_by"] = generated_by
    return assessment


SAFETY_RULES = [
    "Missing camera specifications are never invented; they are flagged 'Site validation required'.",
    "No accuracy figure is guaranteed; success metrics are targets measured in the pilot.",
    "No GPU is stated to support a camera count without benchmark evidence on client streams.",
    "An IP address is not treated as proof of a usable video stream.",
    "An NVR is not assumed to expose RTSP; its capability is verified or flagged.",
    "Anonymous tracking is kept distinct from employee identification; facial recognition is a separately reviewed module.",
    "Privacy, HR and legal approvals are called out wherever identifiable evidence is involved.",
    "New cameras, repositioning or better lighting are stated explicitly where required.",
    "Every calculation carries its formula, inputs and assumptions.",
]


def _collect_assumptions(calcs: dict, comp: dict, st, bitrate_source: str) -> list[str]:
    out = []
    for c in calcs.values():
        out.extend(c.get("assumptions", []))
    out.append(f"Analytics FPS assumed {st.analytics_fps} per stream; model size '{st.model_size}'.")
    out.append("Licence estimate counts class A + B cameras as active; class C/D cameras join after remediation.")
    out.append("Evidence retention uses the client's stated retention period; recordings remain on the client's NVR.")
    return out

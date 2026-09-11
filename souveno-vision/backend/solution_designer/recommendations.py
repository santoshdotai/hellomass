"""Use-case engine, architecture recommendation, risk register and
required client actions. Rule-based; the LLM (narrative.py) only rewrites
these facts into business language and may not add to them."""
from __future__ import annotations

from backend.solution_designer.catalog import SITE_VALIDATION, USE_CASES
from backend.solution_designer.suitability import SuitabilityResult

PRIVACY_NOTE_FR = (
    "Facial recognition / employee identification is NOT part of this design. If the client requires it, "
    "it must be scoped as a separately reviewed module with HR, legal and data-protection sign-off."
)


# ---------------------------------------------------------------- use cases
def use_case_recommendations(selected: list[str], suitability: list[SuitabilityResult]) -> list[dict]:
    out = []
    for uid in selected:
        uc = USE_CASES.get(uid)
        if not uc:
            out.append({"id": uid, "error": "Unknown use case"})
            continue
        fitting = [r for r in suitability if r.use_case_notes.get(uid, {}).get("fit") and r.classification in "AB"]
        needs_validation = [r for r in suitability if r.classification in "AB" and uid not in r.use_case_notes]
        rec = {
            "id": uid,
            "name": uc["name"],
            "required_camera_view": uc["required_view"],
            "suggested_resolution": uc["suggested_resolution"],
            "suggested_analytics_fps": uc["analytics_fps"],
            "camera_placement_requirements": uc["placement"],
            "model_category": uc["model_category"],
            "business_rule": uc["business_rule"],
            "alert_workflow": uc["alert_workflow"],
            "evidence": uc["evidence"],
            "limitations": uc["limitations"],
            "success_metric": uc["success_metric"],
            "privacy_level": uc["privacy_level"],
            "candidate_cameras": [r.label for r in fitting],
            "candidate_camera_count": sum(r.count for r in fitting),
            "approvals_required": [],
        }
        if uc["privacy_level"] == "anonymous_but_hr_sensitive":
            rec["approvals_required"] = [
                "HR policy sign-off: PPE non-compliance evidence involves identifiable staff even though the model is anonymous.",
                "Worker communication/consent per site policy before go-live.",
            ]
        if uid == "restricted_zone":
            rec["approvals_required"].append(
                "Confirm that authorised-vs-unauthorised is decided by schedule/zone rules, not by identifying individuals.")
        if not fitting:
            rec["note"] = ("No camera in the inventory currently satisfies this use case with the data provided. "
                           f"{SITE_VALIDATION} — a new camera, repositioning or better lighting may be required.")
        out.append(rec)
    return out


# ---------------------------------------------------------------- architecture
def stream_architecture(nvr: dict | None, network: dict | None, cameras: list[dict], summary: dict,
                        cloud_allowed: bool | None) -> dict:
    nvr = nvr or {}
    network = network or {}
    total = summary.get("total_cameras", 0)
    candidate = summary.get("candidate_ai_cameras", 0)

    # --- NVR/VMS integration approach
    if nvr.get("rtsp_available") is True:
        integration = "NVR/VMS RTSP re-stream"
        integration_detail = (f"Pull substreams from the {nvr.get('brand') or 'NVR'} {nvr.get('model') or ''} via RTSP. "
                              "The NVR's outbound-stream limit "
                              f"({nvr.get('outbound_stream_limit') if nvr.get('outbound_stream_limit') is not None else 'unknown — ' + SITE_VALIDATION}) "
                              "caps how many cameras can be analysed through it at once.")
    elif nvr.get("api_sdk_available") is True:
        integration = "NVR/VMS SDK / API"
        integration_detail = ("The NVR does not expose RTSP but offers an API/SDK; streams are obtained through the vendor "
                              "SDK. Licensing and SDK stability must be validated in the pilot.")
    elif nvr.get("rtsp_available") is False and nvr.get("api_sdk_available") is False:
        integration = "Bypass NVR — direct camera streams or replacement"
        integration_detail = ("The NVR exposes neither RTSP nor an API. Cameras must be reached directly (IP cameras with "
                              "RTSP) or the recorder must be replaced/augmented with an RTSP-capable device. Analog "
                              "cameras behind this DVR have no usable stream.")
    else:
        integration = f"Undetermined — {SITE_VALIDATION}"
        integration_detail = ("NVR/VMS capabilities were not provided. Do not assume the NVR exposes RTSP; verify per "
                              "channel during the site visit.")

    direct_rtsp = sum(int(c.get("count") or 1) for c in cameras if c.get("rtsp_available") is True)
    if direct_rtsp >= max(candidate, 1) * 0.8:
        stream_source = "Direct camera substreams (RTSP), NVR untouched"
    elif integration.startswith("NVR"):
        stream_source = "Mixed: NVR re-stream where direct RTSP is unavailable, direct camera RTSP elsewhere"
    else:
        stream_source = f"To be confirmed — {SITE_VALIDATION}"

    # --- deployment topology
    if cloud_allowed is False or network.get("internet_restricted"):
        topology = "On-premise GPU server on the camera VLAN; no video leaves the site. Only alert metadata (and optional evidence) leaves via an outbound-only channel if permitted."
    elif total > 60:
        topology = "On-premise GPU server (video stays local); cloud used only for dashboards, alert delivery and model updates."
    else:
        topology = "On-premise edge appliance for inference; cloud dashboard optional."

    return {
        "nvr_integration_approach": integration,
        "nvr_integration_detail": integration_detail,
        "stream_source": stream_source,
        "stream_profile": "Substream at 720p–1080p, H.264, 5–10 FPS, keyframe interval ≤ 2 s — main streams stay on the NVR for recording.",
        "deployment_topology": topology,
        "network_placement": (f"Inference server placed on the camera VLAN ({network.get('camera_vlan') or 'VLAN not specified'}); "
                              f"uplink {network.get('link_speed_mbps') or 'unknown'} Mbps"
                              + (" — verify it exceeds the recommended capacity in the network calculation." if network.get('link_speed_mbps') else f". {SITE_VALIDATION}.")),
        "phased_rollout": [
            f"Phase 0 — Site validation: verify streams, NVR limits, GPU and network for all {total} cameras.",
            "Phase 1 — Technical pilot: 8–12 cameras, 2 areas, 2–3 use cases, 30 days, with benchmarks.",
            f"Phase 2 — Production wave 1: class A cameras ({summary['by_class']['A']['cameras']}) after benchmark-based sizing.",
            f"Phase 3 — Production wave 2: class B cameras ({summary['by_class']['B']['cameras']}) after their configuration fixes.",
            "Phase 4 — Remediation: class C/D cameras only after new cameras / repositioning / lighting are done.",
        ],
        "privacy": PRIVACY_NOTE_FR,
    }


# ---------------------------------------------------------------- risks
def risk_register(cameras: list[dict], nvr: dict | None, server: dict | None, network: dict | None,
                  use_cases: list[str], suitability: list[SuitabilityResult], compute: dict, calcs: dict,
                  privacy: dict | None) -> list[dict]:
    nvr = nvr or {}
    server = server or {}
    network = network or {}
    privacy = privacy or {}
    risks: list[dict] = []

    def add(rid, title, severity, likelihood, impact, mitigation, owner="Souveno + Client"):
        risks.append({"id": rid, "title": title, "severity": severity, "likelihood": likelihood,
                      "impact": impact, "mitigation": mitigation, "owner": owner})

    unknown_cams = sum(r.count for r in suitability if r.validation_items)
    if unknown_cams:
        add("R1", f"Camera specifications incomplete for {unknown_cams} camera(s)", "high", "certain",
            "Suitability scores are provisional; some cameras may prove unusable on site.",
            "Site validation visit with stream capture per camera group before the pilot scope is fixed.")
    if nvr.get("rtsp_available") is None and nvr.get("api_sdk_available") is None:
        add("R2", "NVR/VMS stream export capability unknown", "high", "likely",
            "If the NVR exposes neither RTSP nor an API, no camera behind it can be analysed without changes.",
            "Verify RTSP per channel and outbound-stream limit on the actual NVR model.")
    elif nvr.get("rtsp_available") is False and nvr.get("api_sdk_available") is False:
        add("R2", "NVR/VMS exposes no RTSP or API", "critical", "certain",
            "No usable stream from cameras behind this NVR.",
            "Direct camera RTSP where possible; otherwise replace/augment the recorder. Analog cameras need new IP cameras or encoders.")
    if nvr.get("outbound_stream_limit") and nvr["outbound_stream_limit"] < sum(int(c.get("count") or 1) for c in cameras):
        add("R3", f"NVR outbound-stream limit ({nvr['outbound_stream_limit']}) below camera count", "medium", "certain",
            "Not all cameras can be re-streamed simultaneously via the NVR.",
            "Use direct camera substreams for the remainder or stage rollout in waves.")
    if compute.get("gpu_status") == "none":
        add("R4", "No GPU available", "high", "certain",
            "Production analytics cannot run on the existing server.",
            "Procure a GPU server sized from the pilot benchmark, not from vendor figures.", "Client")
    elif compute.get("gpu_status") in ("unknown", "unrecognised"):
        add("R4", "GPU model unknown or unbenchmarked", "high", "certain",
            "Camera capacity per server cannot be stated; hardware budget is undetermined.",
            "Capture nvidia-smi on site; run the pilot benchmark before quoting hardware.")
    else:
        add("R4", "GPU capacity unbenchmarked on client streams", "medium", "certain",
            "Actual streams-per-GPU may differ from expectations.",
            "Pilot benchmark with representative streams before production sizing.")
    analog = sum(int(c.get("count") or 1) for c in cameras if c.get("camera_type") == "analog_dvr")
    if analog:
        add("R5", f"{analog} analog camera(s) behind DVR", "medium", "certain",
            "DVR re-encoded streams are often low resolution/FPS; identification-grade analytics (PPE) unreliable.",
            "Validate DVR RTSP output quality; plan IP camera replacement for high-value zones.")
    bw = calcs.get("total_stream_bandwidth_mbps", {})
    cap = calcs.get("recommended_network_capacity_mbps", {})
    link = network.get("link_speed_mbps")
    if bw.get("value") is None:
        add("R6", "Stream bitrate unknown — network load not calculable", "medium", "certain",
            "Network may be under-provisioned for analytics substreams.",
            "Measure actual substream bitrate on 3–5 cameras during the site visit.")
    elif link and cap.get("value") and cap["value"] > link:
        add("R6", f"Recommended capacity {cap['value']} Mbps exceeds link {link} Mbps", "high", "certain",
            "Dropped frames and stream instability under load.",
            "Use lower-bitrate substreams, segment VLANs, or upgrade the uplink before the pilot.", "Client")
    elif not link:
        add("R6", "Network link speed not provided", "medium", "likely",
            "Cannot confirm the network can carry the analytics streams.",
            f"Confirm switch/uplink capacity and camera VLAN design. {SITE_VALIDATION}.")
    if network.get("internet_restricted"):
        add("R7", "Internet/cloud restricted", "low", "certain",
            "Cloud dashboards, remote support and model updates need an approved outbound path.",
            "On-premise deployment with an approved outbound-only channel or manual update procedure.")
    if "ppe" in use_cases:
        add("R8", "PPE detection needs site-specific validation and HR approval", "medium", "likely",
            "Generic PPE models mis-classify site-specific gear; evidence involves identifiable staff.",
            "Collect site samples in the pilot; HR/legal sign-off on evidence handling and retention.")
    if "person_down" in use_cases:
        add("R9", "Fall detection false alerts from work postures", "medium", "likely",
            "Alert fatigue if kneeling/bending work is common.",
            "Zone-specific tuning in the pilot; never the sole safety mechanism.")
    if "restricted_zone" in use_cases:
        add("R10", "Restricted-zone rules cannot identify who is authorised", "low", "certain",
            "Authorised staff will trigger alerts unless schedule/zone rules are agreed.",
            "Define allowed hours/roles per zone; identification would be a separate module.")
    if privacy.get("employee_identification_requested"):
        add("R11", "Employee identification requested", "high", "certain",
            "Facial recognition/identification carries legal and HR obligations and is outside this scope.",
            PRIVACY_NOTE_FR, "Client legal/HR")
    add("R12", "Detection accuracy cannot be guaranteed", "medium", "certain",
        "No video-analytics system achieves 100% accuracy; lighting, occlusion and crowding reduce it.",
        "Success metrics defined per use case and measured against ground truth in the pilot.")
    d_cams = sum(r.count for r in suitability if r.classification == "D")
    if d_cams:
        add("R13", f"{d_cams} camera(s) currently unsuitable (class D)", "medium", "certain",
            "These cameras need replacement, repositioning or a new stream path before any analytics.",
            "Scope remediation separately; exclude from licence count until fixed.", "Client")
    return risks


# ---------------------------------------------------------------- client actions
def required_client_actions(suitability: list[SuitabilityResult], nvr: dict | None, server: dict | None,
                            network: dict | None, use_cases: list[str], privacy: dict | None) -> list[str]:
    nvr = nvr or {}
    server = server or {}
    network = network or {}
    actions: list[str] = []
    if any(r.validation_items for r in suitability):
        actions.append("Provide camera make/model, resolution, FPS, codec and RTSP/ONVIF status per camera group (CSV template supplied), or allow a site validation visit.")
    if nvr.get("rtsp_available") is None:
        actions.append(f"Confirm NVR/VMS brand, model, firmware, RTSP per-channel support and outbound-stream limit.")
    if not server.get("nvidia_smi_output") and not server.get("gpu_model"):
        actions.append("Run `nvidia-smi` on the proposed server (or confirm no GPU exists) and share the output.")
    if not network.get("link_speed_mbps"):
        actions.append("Share network switch/uplink capacity and the camera VLAN layout.")
    actions.append("Nominate two pilot areas and a business owner for each pilot use case.")
    actions.append("Provide ground-truth support during the pilot (manual counts / staged events on agreed dates).")
    if "ppe" in use_cases or (privacy or {}).get("employee_identification_requested"):
        actions.append("Obtain HR and legal approval for evidence handling, retention and worker communication before the pilot.")
    actions.extend(sorted({a for r in suitability for a in r.required_actions}))
    return actions

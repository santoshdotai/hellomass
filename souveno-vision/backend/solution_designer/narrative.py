"""Narrative layer: turns the deterministic assessment into business-friendly
prose. Two paths, always in this order:

  1. rule-based templates (the real fallback, works with no API key);
  2. optional LLM rewrite via the Anthropic SDK when LLM_API_KEY is set.

The LLM receives ONLY the structured findings and is instructed never to
add numbers, camera specs, capacity claims or accuracy guarantees. Its
output is post-checked for forbidden claims; if any are found the
rule-based text is used instead.
"""
from __future__ import annotations

import json
import re

from config.settings import settings

FORBIDDEN_PATTERNS = [
    r"100\s*%\s*accura", r"guarantee[ds]?\s+(?:accuracy|compatib|capacity)", r"will\s+(?:definitely|certainly)\s+support",
    r"can\s+(?:easily\s+)?handle\s+\d+\s+cameras", r"facial\s+recognition\s+(?:is|will\s+be)\s+(?:included|enabled)",
]

SYSTEM_PROMPT = """You are the Souveno Vision solution architect writing for a business audience.
You will receive a JSON document of findings produced by deterministic rules and calculators.
Rewrite the requested sections in clear, plain, non-technical business language.

Hard rules — violating any of them makes your output unusable:
- Use only facts, numbers and camera details present in the JSON. Never invent or infer camera
  specifications, GPU capacity, stream availability or accuracy figures.
- Never state or imply 100% accuracy, guaranteed compatibility, or that a GPU can process a
  given number of cameras. Where the JSON says benchmarking is required, say so.
- Anything marked "Site validation required" stays flagged as unverified.
- An IP address is not proof of a usable video stream; an NVR is not assumed to expose RTSP.
- Keep anonymous tracking distinct from employee identification; facial recognition is only
  ever a separately reviewed module needing HR/legal approval.
- Say plainly when a new camera, repositioning or better lighting is required.
- Return JSON with exactly the keys requested and string values only."""


def _fmt_inr(x: float | int) -> str:
    """Indian digit grouping: 4,47,840."""
    n = int(round(x))
    s = str(abs(n))
    if len(s) <= 3:
        out = s
    else:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        out = ",".join(parts) + "," + tail
    return ("-" if n < 0 else "") + "₹" + out


def rule_based_sections(a: dict) -> dict:
    """Plain-language sections derived purely from the assessment dict."""
    client = a["input"]["client"]
    site = a["input"]["site"]
    s = a["suitability_summary"]
    comp = a["compute"]
    pilot = a["pilot"]
    calcs = a["calculations"]
    est = a["commercial"]
    uc_names = [u["name"] for u in a["use_cases"] if "name" in u]
    bw = calcs["total_stream_bandwidth_mbps"]["value"]
    cap = calcs["recommended_network_capacity_mbps"]["value"]

    exec_summary = (
        f"{client['company_name']} asked Souveno to assess {site['name']} "
        f"({s['total_cameras']} cameras across the inventory provided"
        + (f", {site['employees']} employees" if site.get("employees") else "") + ") for AI video analytics covering "
        + ", ".join(uc_names) + ". "
        f"Based on the information supplied, {s['by_class']['A']['cameras']} cameras are AI-ready, "
        f"{s['by_class']['B']['cameras']} are usable after configuration, {s['by_class']['C']['cameras']} support only basic analytics "
        f"and {s['by_class']['D']['cameras']} are unsuitable as they stand. "
        f"{s['validation_required_cameras']} cameras have gaps in their specifications that must be validated on site before "
        "any figure in this document is treated as final. "
    )
    if not comp["benchmark_available"]:
        exec_summary += ("Because no benchmark exists for the client's streams on the available GPU"
                         + (" (which is itself unknown)" if comp["gpu_status"] in ("unknown", "unrecognised") else
                            " (none is available)" if comp["gpu_status"] == "none" else "")
                         + ", Souveno recommends a 30-day technical pilot on "
                         f"{pilot['camera_count']} representative cameras before any production hardware or camera count is committed. ")
    exec_summary += (f"The preliminary software estimate for {est['active_ai_cameras']} candidate cameras is "
                     f"{_fmt_inr(est['monthly_licence']['ex_gst'])} per month plus GST, with one-time fees of "
                     f"{_fmt_inr(est['one_time_total']['ex_gst'])} plus GST; hardware is excluded until benchmarking.")

    objectives = ("The client wants to " + "; ".join(
        f"{u['name'].lower()} — {(u['business_rule'][0].lower() + u['business_rule'][1:]).rstrip('.')}" for u in a["use_cases"] if "name" in u
    ) + ". Alerts must reach the responsible person within "
        + (f"{a['input']['requirements'].get('required_alert_latency_s')} seconds" if a['input']['requirements'].get('required_alert_latency_s') else "a latency still to be agreed")
        + ". All analytics are anonymous: people are tracked as numbered objects, not identified.")

    infra = (
        f"The site reports {site.get('existing_camera_count') or s['total_cameras']} cameras. "
        + (f"Recording is on a {a['input']['nvr'].get('brand') or 'NVR'} {a['input']['nvr'].get('model') or ''}; " if a["input"].get("nvr") else "No NVR details were supplied; ")
        + a["architecture"]["nvr_integration_detail"] + " "
        + (comp["findings"][0] if comp["findings"] else "No server details were supplied.") + " "
        + ("Network: " + a["architecture"]["network_placement"])
    )

    network = (
        f"With {calcs['total_stream_bandwidth_mbps']['inputs']['active_stream_count']} active analytics streams at "
        f"{calcs['total_stream_bandwidth_mbps']['inputs']['average_stream_bitrate_mbps']} Mbps each, the analytics traffic is "
        + (f"{bw} Mbps, and Souveno recommends provisioning {cap} Mbps (safety factor {calcs['recommended_network_capacity_mbps']['inputs']['safety_factor']}×)."
           if bw is not None else "not yet calculable because the stream bitrate is unknown — it must be measured on site.")
        + f" The analytics engine will process about {calcs['analysed_frames_per_second']['value']} frames per second in total. "
        f"Evidence clips need roughly {calcs['estimated_evidence_storage_gb']['value']} GB for the retention period; continuous recording stays on the existing NVR."
    )

    compute_text = (" ".join(comp["findings"]) + " " + " ".join(comp["warnings"]) + " " + comp["capacity_statement"]
                    + " " + comp["recommendation"]).strip()

    pilot_text = (
        f"Souveno proposes a {pilot['duration_days']}-day technical pilot on {pilot['camera_count']} cameras across "
        + " and ".join(pilot["areas"]) + ", covering " + ", ".join(u["name"].lower() for u in pilot["use_cases"]) + ". "
        "The pilot measures accuracy against ground truth, false alerts, stream stability, GPU utilisation and network load, "
        "and ends with a go/no-go decision against written scale-up criteria."
    )
    commercial_text = (
        f"This is a preliminary estimate. Software licence: {_fmt_inr(est['monthly_licence']['ex_gst'])} per month "
        f"({_fmt_inr(est['annual_licence']['ex_gst'])} per year) for {est['active_ai_cameras']} active AI cameras, tiered per the schedule. "
        f"One-time: technical pilot {_fmt_inr(est['technical_pilot']['ex_gst'])} and production implementation "
        f"{_fmt_inr(est['one_time_implementation']['ex_gst'])}. First-year total {_fmt_inr(est['first_year_total']['ex_gst'])} plus GST "
        f"{_fmt_inr(est['first_year_total']['gst'])}; second-year software {_fmt_inr(est['second_year_software_total']['ex_gst'])} plus GST. "
        "Hardware, custom models and external integrations are excluded."
    )
    return {
        "executive_summary": exec_summary,
        "client_objectives": objectives,
        "existing_infrastructure": infra,
        "network_narrative": network,
        "compute_narrative": compute_text,
        "pilot_narrative": pilot_text,
        "commercial_narrative": commercial_text,
    }


NEGATIONS = re.compile(r"\b(no|not|never|cannot|can't|without|does not|is not|neither)\b", re.IGNORECASE)


def _violates(text: str) -> bool:
    """True when any sentence makes an affirmative forbidden claim. A sentence
    that negates the claim ("no system achieves 100% accuracy") is allowed."""
    plain = re.sub(r"<[^>]+>", " ", text)
    for sentence in re.split(r"(?<=[.;!?])\s+|\n+", plain):
        if any(re.search(p, sentence, re.IGNORECASE) for p in FORBIDDEN_PATTERNS) and not NEGATIONS.search(sentence):
            return True
    return False


def llm_sections(a: dict, base: dict) -> dict | None:
    """Rewrite the rule-based sections with the LLM. Returns None when no
    LLM is configured or the output fails the safety check."""
    if not settings.llm_api_key:
        return None
    try:
        import anthropic
    except ImportError:
        return None
    facts = {
        "client": a["input"]["client"], "site": a["input"]["site"],
        "suitability_summary": a["suitability_summary"],
        "calculations": a["calculations"], "compute": {k: v for k, v in a["compute"].items() if k != "nvidia_smi_parsed"},
        "architecture": a["architecture"], "pilot": {k: v for k, v in a["pilot"].items() if k != "cameras"},
        "commercial": {k: v for k, v in a["commercial"].items() if k != "pricing_config_used"},
        "risks": a["risks"], "draft_sections": base,
    }
    prompt = (
        "Rewrite each of the following draft sections for a client-facing proposal. Keep every number and caveat. "
        "Return a JSON object with keys: " + ", ".join(base.keys()) + ".\n\nFINDINGS:\n" + json.dumps(facts, default=str)
    )
    try:
        client = anthropic.Anthropic(api_key=settings.llm_api_key)
        response = client.messages.create(
            model=settings.llm_model,
            max_tokens=6000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        if response.stop_reason == "refusal":
            return None
        text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
        m = re.search(r"\{.*\}", text, re.DOTALL)
        data = json.loads(m.group(0) if m else text)
    except Exception:
        return None
    out = {}
    for k in base:
        v = data.get(k)
        if not isinstance(v, str) or not v.strip() or _violates(v):
            return None
        out[k] = v.strip()
    return out


def build_narrative(a: dict) -> tuple[dict, str]:
    base = rule_based_sections(a)
    llm = llm_sections(a, base)
    if llm:
        return llm, "llm"
    return base, "rule_based"

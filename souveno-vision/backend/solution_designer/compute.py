"""Preliminary compute workload calculator.

Builds a workload profile from the assessment and reports what is known
about the server/GPU. It never converts VRAM into a camera count. Where
benchmark data is unavailable (which is the default for every GPU in the
catalogue), it says so verbatim and recommends a pilot benchmark.
"""
from __future__ import annotations

import re

from backend.solution_designer.catalog import (
    GPU_CAPACITY_DISCLAIMER, GPU_CATALOG, MODEL_SIZES, RESOLUTIONS, normalise_gpu_name,
)


def parse_nvidia_smi(text: str | None) -> list[dict]:
    """Extract GPU name, VRAM (MiB, total/used) and utilisation from raw
    `nvidia-smi` output or `nvidia-smi --query-gpu=... --format=csv` output.
    Returns [] when nothing recognisable is found."""
    if not text:
        return []
    gpus: list[dict] = []
    # CSV query format: name, memory.total [MiB], memory.used [MiB], utilization.gpu [%]
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 2 and "nvidia" in parts[0].lower() and not line.strip().startswith("|"):
            g = {"name": parts[0], "vram_total_mib": None, "vram_used_mib": None, "utilization_pct": None}
            for p in parts[1:]:
                m = re.match(r"(\d+)\s*MiB", p)
                if m and g["vram_total_mib"] is None:
                    g["vram_total_mib"] = int(m.group(1)); continue
                if m and g["vram_used_mib"] is None:
                    g["vram_used_mib"] = int(m.group(1)); continue
                m = re.match(r"(\d+)\s*%", p)
                if m:
                    g["utilization_pct"] = int(m.group(1))
            gpus.append(g)
    if gpus:
        return gpus
    # Table format
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = re.search(r"\|\s+\d+\s+(NVIDIA[^|]+?)\s{2,}", line) or re.search(r"\|\s+\d+\s+([A-Za-z][^|]+?)\s+(?:On|Off)\s*\|", line)
        if m and i + 1 < len(lines):
            name = m.group(1).strip()
            nxt = lines[i + 1]
            mem = re.search(r"(\d+)MiB\s*/\s*(\d+)MiB", nxt)
            util = re.search(r"(\d+)%\s+Default", nxt) or re.search(r"\|\s*(\d+)%", nxt)
            gpus.append({
                "name": name,
                "vram_used_mib": int(mem.group(1)) if mem else None,
                "vram_total_mib": int(mem.group(2)) if mem else None,
                "utilization_pct": int(util.group(1)) if util else None,
            })
    return gpus


def _megapixels(resolution: str | None) -> float | None:
    if not resolution:
        return None
    r = RESOLUTIONS.get(str(resolution).lower())
    return r[2] if r else None


def workload_profile(cameras: list[dict], use_cases: list[str], analytics_fps: float,
                     model_size: str, model_count: int, tracking: bool,
                     required_alert_latency_s: float | None, evidence_encoding: bool) -> dict:
    """Aggregate decode + inference demand. Units are illustrative and only
    for comparing scenarios — they are not a capacity claim."""
    total_streams = sum(int(c.get("count") or 1) for c in cameras)
    known_mp = []
    unknown_res = 0
    hevc = 0
    for c in cameras:
        n = int(c.get("count") or 1)
        mp = _megapixels(c.get("resolution"))
        if mp is None:
            unknown_res += n
        else:
            known_mp.extend([mp] * n)
        if (c.get("codec") or "").lower() == "h265":
            hevc += n
    avg_mp = sum(known_mp) / len(known_mp) if known_mp else None
    decode_mpx_s = None if avg_mp is None else round(avg_mp * total_streams * min(analytics_fps, 30), 1)
    rel = MODEL_SIZES.get(model_size, MODEL_SIZES["nano"])["relative_cost"]
    inference_units = round(total_streams * analytics_fps * rel * max(model_count, 1) * (1.15 if tracking else 1.0), 1)
    return {
        "total_streams": total_streams,
        "analytics_fps": analytics_fps,
        "analysed_frames_per_second": round(total_streams * analytics_fps, 1),
        "average_megapixels": None if avg_mp is None else round(avg_mp, 2),
        "streams_with_unknown_resolution": unknown_res,
        "hevc_streams": hevc,
        "decode_load_megapixels_per_second": decode_mpx_s,
        "model_size": model_size,
        "model_count": model_count,
        "tracking_enabled": tracking,
        "evidence_encoding": evidence_encoding,
        "required_alert_latency_s": required_alert_latency_s,
        "relative_inference_units": inference_units,
        "note": "Relative inference units = streams × analytics FPS × model cost factor × model count × tracking factor. "
                "For scenario comparison only; it is not a GPU capacity figure.",
    }


def assess_compute(server: dict | None, cameras: list[dict], use_cases: list[str], analytics_fps: float,
                   model_size: str = "small", model_count: int | None = None, tracking: bool = True,
                   required_alert_latency_s: float | None = None, evidence_encoding: bool = True) -> dict:
    server = server or {}
    if model_count is None:
        # One detector, plus a pose model for falls, plus an attribute head for PPE.
        model_count = 1 + (1 if "person_down" in use_cases else 0) + (1 if "ppe" in use_cases else 0)

    profile = workload_profile(cameras, use_cases, analytics_fps, model_size, model_count, tracking,
                               required_alert_latency_s, evidence_encoding)

    smi = parse_nvidia_smi(server.get("nvidia_smi_output"))
    gpu_name = server.get("gpu_model") or (smi[0]["name"] if smi else None)
    gpu_key = normalise_gpu_name(gpu_name)
    gpu_ref = GPU_CATALOG.get(gpu_key) if gpu_key else None
    vram_gb = server.get("gpu_vram_gb")
    if vram_gb is None and smi and smi[0].get("vram_total_mib"):
        vram_gb = round(smi[0]["vram_total_mib"] / 1024, 1)
    util = server.get("existing_gpu_utilization_pct")
    if util is None and smi and smi[0].get("utilization_pct") is not None:
        util = smi[0]["utilization_pct"]

    findings: list[str] = []
    warnings: list[str] = []
    gpu_status = "unknown"

    if server.get("has_gpu") is False or (gpu_name is None and server.get("has_gpu") is None and not smi and server and server.get("cpu_model")):
        if server.get("has_gpu") is False:
            gpu_status = "none"
            findings.append("No GPU is available on the existing server.")
            warnings.append("CPU-only inference is limited to a handful of low-FPS streams and is not suitable for "
                            "production analytics at this camera count. A GPU server (specified after the pilot benchmark) "
                            "is required.")
        else:
            gpu_status = "unknown"
    if gpu_status == "unknown" and (gpu_name is None and not smi):
        findings.append("GPU model is unknown — no nvidia-smi output or GPU model was supplied.")
        warnings.append("Unknown GPU: no capacity statement is possible. Collect `nvidia-smi` output during the site visit.")
    elif gpu_name:
        gpu_status = "known" if gpu_ref else "unrecognised"
        findings.append(f"GPU reported: {gpu_name}" + (f" ({gpu_ref['name']}, {gpu_ref['nvdec_engines']} NVDEC engine(s), "
                                                       f"HEVC decode {'yes' if gpu_ref['hevc'] else 'no'})" if gpu_ref else " — not in the reference table."))
        if not gpu_ref:
            warnings.append("GPU model not in Souveno's reference table; decoder capability must be checked from the vendor datasheet.")
        if profile["hevc_streams"] and gpu_ref and not gpu_ref["hevc"]:
            warnings.append("H.265 streams present but the GPU has no HEVC hardware decoder.")
    if vram_gb is not None:
        findings.append(f"GPU VRAM: {vram_gb} GB. VRAM alone does not determine camera capacity — decoder throughput, "
                        "model size and analytics FPS usually bind first.")
    if util is not None:
        findings.append(f"Existing GPU utilisation: {util}%.")
        if util >= 40:
            warnings.append(f"GPU already {util}% utilised by other workloads; only the remaining headroom is available.")
    if server.get("cpu_cores"):
        findings.append(f"CPU: {server.get('cpu_model') or 'unspecified'} ({server['cpu_cores']} cores).")
    if server.get("ram_gb"):
        findings.append(f"RAM: {server['ram_gb']} GB.")
    if profile["streams_with_unknown_resolution"]:
        warnings.append(f"{profile['streams_with_unknown_resolution']} stream(s) have unknown resolution; decode load cannot be computed for them.")
    if required_alert_latency_s is not None and required_alert_latency_s < 2:
        warnings.append(f"Required alert latency of {required_alert_latency_s} s leaves no room for batching; expect lower streams per GPU.")

    benchmark_available = bool(gpu_ref and gpu_ref.get("benchmark_available"))
    capacity_statement = GPU_CAPACITY_DISCLAIMER
    indicative = None
    if benchmark_available:
        indicative = gpu_ref.get("benchmark")  # would carry measured streams/GPU by profile
        capacity_statement = "Indicative capacity from Souveno benchmark data; still to be confirmed on client streams."

    return {
        "gpu_status": gpu_status,
        "gpu_model": gpu_name,
        "gpu_reference": gpu_ref,
        "gpu_vram_gb": vram_gb,
        "existing_gpu_utilization_pct": util,
        "nvidia_smi_parsed": smi,
        "workload_profile": profile,
        "factors_considered": [
            "GPU model", "decoder capability (NVDEC engines, HEVC)", "codec mix", "resolution", "analytics FPS",
            "model size", "number of models", "tracking", "required alert latency", "concurrent streams",
            "evidence encoding", "existing server utilisation",
        ],
        "findings": findings,
        "warnings": warnings,
        "benchmark_available": benchmark_available,
        "capacity_statement": capacity_statement,
        "indicative_capacity": indicative,
        "recommendation": (
            "Run a pilot benchmark on representative client streams (same codec, resolution and FPS as production) "
            "and measure decode utilisation, GPU utilisation, end-to-end latency and dropped frames before sizing "
            "production hardware."
        ),
        "final_hardware_can_be_recommended": False if not benchmark_available else True,
    }

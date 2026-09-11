"""Deterministic calculators.

Every function returns a dict with `value`, `formula`, `inputs` and
`assumptions` so the number is traceable end-to-end in the report and can
never be silently changed by a prompt. None of these functions is ever
exposed to the LLM as a tool; the LLM only receives their outputs.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Calculation:
    name: str
    value: float | None
    unit: str
    formula: str
    inputs: dict
    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "formula": self.formula,
            "inputs": self.inputs,
            "assumptions": self.assumptions,
            "warnings": self.warnings,
        }


def _r(x: float | None, nd: int = 2) -> float | None:
    return None if x is None else round(x, nd)


def total_stream_bandwidth(active_stream_count: int, average_stream_bitrate_mbps: float | None,
                           bitrate_source: str = "measured") -> Calculation:
    """total_stream_bandwidth_mbps = active_stream_count × average_stream_bitrate_mbps"""
    warnings: list[str] = []
    assumptions: list[str] = []
    if average_stream_bitrate_mbps is None or average_stream_bitrate_mbps <= 0:
        return Calculation(
            "total_stream_bandwidth_mbps", None, "Mbps",
            "total_stream_bandwidth_mbps = active_stream_count × average_stream_bitrate_mbps",
            {"active_stream_count": active_stream_count, "average_stream_bitrate_mbps": average_stream_bitrate_mbps},
            warnings=["Average stream bitrate unknown — bandwidth cannot be calculated. Site validation required."],
        )
    if bitrate_source != "measured":
        assumptions.append(
            f"Average bitrate of {average_stream_bitrate_mbps} Mbps is {bitrate_source}, not measured on site."
        )
    value = active_stream_count * average_stream_bitrate_mbps
    return Calculation(
        "total_stream_bandwidth_mbps", _r(value), "Mbps",
        "total_stream_bandwidth_mbps = active_stream_count × average_stream_bitrate_mbps",
        {"active_stream_count": active_stream_count, "average_stream_bitrate_mbps": average_stream_bitrate_mbps},
        assumptions, warnings,
    )


def recommended_network_capacity(total_bandwidth_mbps: float | None, safety_factor: float = 1.5) -> Calculation:
    """recommended_network_capacity = total_stream_bandwidth × safety_factor"""
    if safety_factor < 1.0:
        raise ValueError("safety_factor must be ≥ 1.0")
    if total_bandwidth_mbps is None:
        return Calculation(
            "recommended_network_capacity_mbps", None, "Mbps",
            "recommended_network_capacity = total_stream_bandwidth × safety_factor",
            {"total_stream_bandwidth_mbps": None, "safety_factor": safety_factor},
            warnings=["Depends on total stream bandwidth, which is unknown."],
        )
    return Calculation(
        "recommended_network_capacity_mbps", _r(total_bandwidth_mbps * safety_factor), "Mbps",
        "recommended_network_capacity = total_stream_bandwidth × safety_factor",
        {"total_stream_bandwidth_mbps": total_bandwidth_mbps, "safety_factor": safety_factor},
        [f"Safety factor {safety_factor}× covers bitrate bursts (motion, night noise) and management traffic."],
    )


def analysed_frames_per_second(active_stream_count: int, analytics_fps: float) -> Calculation:
    """analysed_frames_per_second = active_stream_count × analytics_fps"""
    if analytics_fps <= 0:
        raise ValueError("analytics_fps must be > 0")
    return Calculation(
        "analysed_frames_per_second", _r(active_stream_count * analytics_fps, 1), "frames/s",
        "analysed_frames_per_second = active_stream_count × analytics_fps",
        {"active_stream_count": active_stream_count, "analytics_fps": analytics_fps},
        ["Analytics FPS is the sampled inference rate, not the camera's native FPS."],
    )


def estimated_evidence_storage(events_per_day: float, average_clip_size_mb: float, retention_days: int,
                               camera_count: int = 1) -> Calculation:
    """estimated_evidence_storage = events_per_day × average_clip_size × retention_days

    `events_per_day` is per camera; the result is multiplied by camera_count
    and reported in GB so the per-camera formula stays exactly as specified.
    """
    if retention_days < 0 or events_per_day < 0 or average_clip_size_mb < 0:
        raise ValueError("storage inputs must be non-negative")
    per_camera_mb = events_per_day * average_clip_size_mb * retention_days
    total_gb = per_camera_mb * camera_count / 1024.0
    return Calculation(
        "estimated_evidence_storage_gb", _r(total_gb), "GB",
        "estimated_evidence_storage = events_per_day × average_clip_size × retention_days (× camera_count)",
        {"events_per_day_per_camera": events_per_day, "average_clip_size_mb": average_clip_size_mb,
         "retention_days": retention_days, "camera_count": camera_count,
         "per_camera_storage_mb": _r(per_camera_mb)},
        ["Evidence storage covers event clips and snapshots only, not continuous recording (that stays on the NVR).",
         f"Average clip size {average_clip_size_mb} MB assumes ~15 s at 1080p H.264; adjust after the pilot."],
    )


def run_all(active_stream_count: int, average_stream_bitrate_mbps: float | None, bitrate_source: str,
            safety_factor: float, analytics_fps: float, events_per_day: float, average_clip_size_mb: float,
            retention_days: int, camera_count: int) -> dict:
    bw = total_stream_bandwidth(active_stream_count, average_stream_bitrate_mbps, bitrate_source)
    cap = recommended_network_capacity(bw.value, safety_factor)
    fps = analysed_frames_per_second(active_stream_count, analytics_fps)
    storage = estimated_evidence_storage(events_per_day, average_clip_size_mb, retention_days, camera_count)
    return {c.name: c.as_dict() for c in (bw, cap, fps, storage)}

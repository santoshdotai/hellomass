"""Sample assessment used by the demo script and the report tests:
348 cameras, 1,000 employees, mixed/unknown camera specs, an existing NVR
of unknown streaming capability, unknown GPU, and restricted-zone,
occupancy and PPE requirements."""
from __future__ import annotations

from backend.solution_designer.schemas import AssessmentRequest


def sample_request() -> AssessmentRequest:
    return AssessmentRequest(
        client={"company_name": "Bharat Precision Components Pvt Ltd", "contact_name": "Plant Head",
                "industry": "manufacturing"},
        site={"name": "Pune Plant 2", "city": "Pune", "employees": 1000, "shifts": 3,
              "existing_camera_count": 348, "operating_hours": "24x7, three shifts"},
        cameras=[
            {"ref": "G1", "name": "Assembly hall domes", "count": 96, "area": "Assembly Hall", "make_model": "Hikvision DS-2CD2143G2",
             "camera_type": "ip_fixed", "resolution": "4mp", "fps": 15, "bitrate_mbps": 4, "codec": "h264",
             "rtsp_available": True, "onvif_available": True, "substream_available": True, "is_ptz": False,
             "view_type": "oblique", "lighting": "good", "occlusion": "partial", "stream_stability": None,
             "subject_distance_m": 10, "use_cases": ["ppe", "occupancy", "restricted_zone"]},
            {"ref": "G2", "name": "Warehouse bullets", "count": 64, "area": "Warehouse", "make_model": "CP Plus (model unknown)",
             "camera_type": "ip_fixed", "resolution": "1080p", "fps": None, "bitrate_mbps": None, "codec": "h265",
             "rtsp_available": None, "onvif_available": None, "is_ptz": False, "view_type": "oblique",
             "lighting": "variable", "use_cases": ["restricted_zone", "occupancy"]},
            {"ref": "G3", "name": "Perimeter PTZ", "count": 8, "area": "Perimeter", "camera_type": "ip_ptz",
             "resolution": "1080p", "fps": 25, "codec": "h264", "rtsp_available": True, "is_ptz": True,
             "lighting": "ir_night", "use_cases": ["restricted_zone"]},
            {"ref": "G4", "name": "Legacy analog cameras (old block)", "count": 80, "area": "Old Block",
             "camera_type": "analog_dvr", "resolution": "d1", "use_cases": ["occupancy"]},
            {"ref": "G5", "name": "Paint shop (specs unknown)", "count": 40, "area": "Paint Shop",
             "camera_type": "unknown", "use_cases": ["ppe", "restricted_zone"]},
            # remaining 60 cameras: no inventory at all → expanded as 'unspecified'
        ],
        nvr={"brand": "Hikvision", "model": "DS-96128NI-I16 (to be confirmed)", "channel_count": 256,
             "rtsp_available": None, "api_sdk_available": None, "outbound_stream_limit": None, "is_dvr": None,
             "notes": "Second recorder for the old block is a DVR; model unknown."},
        server={"has_gpu": None, "cpu_model": "Xeon Silver (model unconfirmed)", "cpu_cores": 16, "ram_gb": 64,
                "gpu_model": None, "nvidia_smi_output": None, "notes": "IT believes a GPU may exist; not verified."},
        network={"link_speed_mbps": 1000, "camera_vlan": "VLAN 40", "internet_restricted": True, "cloud_allowed": False},
        requirements={"use_cases": ["restricted_zone", "occupancy", "ppe"], "required_alert_latency_s": 10,
                      "operating_schedule": "24x7", "privacy_requirements": "No employee identification; union agreement.",
                      "employee_identification_requested": False, "evidence_retention_days": 30,
                      "events_per_camera_per_day": 20, "average_clip_size_mb": 5},
        settings={"network_safety_factor": 1.5, "analytics_fps": 5, "assumed_bitrate_mbps": 3.0, "model_size": "small"},
    )

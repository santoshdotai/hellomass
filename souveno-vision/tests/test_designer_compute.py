from backend.solution_designer.compute import assess_compute, parse_nvidia_smi
from backend.solution_designer.catalog import GPU_CAPACITY_DISCLAIMER

CAMS = [{"count": 50, "resolution": "1080p", "codec": "h264"}, {"count": 20, "resolution": "4mp", "codec": "h265"}]

SMI_TABLE = """+-----------------------------------------------------------------------------+
| NVIDIA-SMI 535.104.05   Driver Version: 535.104.05   CUDA Version: 12.2     |
|-------------------------------+----------------------+----------------------+
| GPU  Name        Persistence-M| Bus-Id        Disp.A | Volatile Uncorr. ECC |
|===============================+======================+======================|
|   0  Tesla T4            On   | 00000000:00:04.0 Off |                    0 |
| N/A   45C    P0    28W /  70W |   3200MiB / 15360MiB |     12%      Default |
+-------------------------------+----------------------+----------------------+"""


def test_no_gpu_scenario():
    out = assess_compute({"has_gpu": False, "cpu_model": "Xeon", "cpu_cores": 16}, CAMS, ["occupancy"], 5)
    assert out["gpu_status"] == "none"
    assert any("CPU-only" in w for w in out["warnings"])
    assert out["capacity_statement"] == GPU_CAPACITY_DISCLAIMER
    assert out["final_hardware_can_be_recommended"] is False
    assert "benchmark" in out["recommendation"].lower()


def test_unknown_gpu_gives_benchmark_warning_and_no_capacity_number():
    out = assess_compute({"has_gpu": None}, CAMS, ["ppe"], 5)
    assert out["gpu_status"] == "unknown"
    assert any("Unknown GPU" in w for w in out["warnings"])
    assert out["capacity_statement"] == GPU_CAPACITY_DISCLAIMER
    assert out["indicative_capacity"] is None
    assert out["benchmark_available"] is False


def test_known_gpu_still_requires_benchmark_and_never_uses_vram_alone():
    out = assess_compute({"gpu_model": "NVIDIA A10", "gpu_vram_gb": 24}, CAMS, ["ppe"], 5)
    assert out["gpu_status"] == "known"
    assert out["gpu_reference"]["name"] == "NVIDIA A10"
    assert out["capacity_statement"] == GPU_CAPACITY_DISCLAIMER
    assert any("VRAM alone does not determine" in f for f in out["findings"])
    assert "decoder capability (NVDEC engines, HEVC)" in out["factors_considered"]
    assert out["workload_profile"]["model_count"] == 2  # detector + PPE head


def test_nvidia_smi_table_parsed_and_used():
    gpus = parse_nvidia_smi(SMI_TABLE)
    assert gpus[0]["name"] == "Tesla T4" and gpus[0]["vram_total_mib"] == 15360 and gpus[0]["utilization_pct"] == 12
    out = assess_compute({"nvidia_smi_output": SMI_TABLE}, CAMS, ["occupancy"], 5)
    assert out["gpu_model"] == "Tesla T4" and out["gpu_reference"]["name"] == "NVIDIA T4"
    assert out["gpu_vram_gb"] == 15.0
    assert out["existing_gpu_utilization_pct"] == 12


def test_nvidia_smi_csv_parsed():
    csv = "name, memory.total [MiB], memory.used [MiB], utilization.gpu [%]\nNVIDIA GeForce RTX 4090, 24564 MiB, 9000 MiB, 55 %\n"
    gpus = parse_nvidia_smi(csv)
    assert gpus[0]["vram_total_mib"] == 24564 and gpus[0]["utilization_pct"] == 55
    out = assess_compute({"nvidia_smi_output": csv}, CAMS, ["occupancy"], 5)
    assert any("already 55% utilised" in w for w in out["warnings"])


def test_unrecognised_gpu_warns():
    out = assess_compute({"gpu_model": "Intel Arc A770"}, CAMS, ["occupancy"], 5)
    assert out["gpu_status"] == "unrecognised"
    assert any("not in Souveno's reference table" in w for w in out["warnings"])


def test_tight_latency_and_unknown_resolution_warnings():
    out = assess_compute({"gpu_model": "T4"}, CAMS + [{"count": 3}], ["line_crossing"], 10, required_alert_latency_s=1)
    assert any("latency" in w for w in out["warnings"])
    assert any("unknown resolution" in w for w in out["warnings"])

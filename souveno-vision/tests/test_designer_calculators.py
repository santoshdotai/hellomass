import pytest

from backend.solution_designer import calculators as calc
from backend.solution_designer.pricing import commercial_estimate, tiered_monthly_licence, validate_pricing, DEFAULT_PRICING


# ---------------------------------------------------------------- bandwidth
def test_total_stream_bandwidth_is_count_times_bitrate():
    c = calc.total_stream_bandwidth(348, 4.0)
    assert c.value == 1392.0
    assert c.formula == "total_stream_bandwidth_mbps = active_stream_count × average_stream_bitrate_mbps"
    assert c.inputs == {"active_stream_count": 348, "average_stream_bitrate_mbps": 4.0}


def test_bandwidth_with_unknown_bitrate_returns_none_and_warns():
    c = calc.total_stream_bandwidth(100, None)
    assert c.value is None
    assert any("Site validation required" in w for w in c.warnings)


def test_assumed_bitrate_is_recorded_as_assumption():
    c = calc.total_stream_bandwidth(10, 3.0, bitrate_source="assumed")
    assert c.value == 30.0
    assert any("assumed" in a for a in c.assumptions)


def test_network_capacity_applies_safety_factor():
    c = calc.recommended_network_capacity(1392.0, 1.5)
    assert c.value == 2088.0
    with pytest.raises(ValueError):
        calc.recommended_network_capacity(100.0, 0.9)


def test_network_capacity_propagates_unknown():
    assert calc.recommended_network_capacity(None, 1.5).value is None


def test_analysed_fps():
    assert calc.analysed_frames_per_second(104, 5).value == 520.0
    with pytest.raises(ValueError):
        calc.analysed_frames_per_second(10, 0)


# ---------------------------------------------------------------- evidence storage
def test_evidence_storage_formula():
    # 20 events/day × 5 MB × 30 days = 3000 MB per camera; × 104 cameras = 312000 MB = 304.69 GB
    c = calc.estimated_evidence_storage(20, 5, 30, camera_count=104)
    assert c.inputs["per_camera_storage_mb"] == 3000.0
    assert c.value == round(312000 / 1024, 2)
    assert "events_per_day × average_clip_size × retention_days" in c.formula


def test_evidence_storage_rejects_negative():
    with pytest.raises(ValueError):
        calc.estimated_evidence_storage(-1, 5, 30)


def test_run_all_returns_every_calculation_with_formula():
    out = calc.run_all(104, 3.28, "assumed", 1.5, 5, 20, 5, 30, 104)
    assert set(out) == {"total_stream_bandwidth_mbps", "recommended_network_capacity_mbps",
                        "analysed_frames_per_second", "estimated_evidence_storage_gb"}
    for c in out.values():
        assert c["formula"] and "inputs" in c and "assumptions" in c


# ---------------------------------------------------------------- tiered pricing
@pytest.mark.parametrize("cameras,expected", [
    (0, 0),
    (1, 1500),
    (50, 75_000),
    (51, 75_000 + 1200),
    (150, 75_000 + 120_000),
    (151, 75_000 + 120_000 + 900),
    (348, 75_000 + 120_000 + 198 * 900),
])
def test_tiered_monthly_licence(cameras, expected):
    assert tiered_monthly_licence(cameras, DEFAULT_PRICING["licence_tiers"])["monthly_licence"] == expected


def test_tier_breakdown_slices_cameras_correctly():
    b = tiered_monthly_licence(348, DEFAULT_PRICING["licence_tiers"])["breakdown"]
    assert [t["cameras"] for t in b] == [50, 100, 198]


def test_commercial_estimate_shows_gst_and_pilot_separately():
    est = commercial_estimate(348)
    assert est["monthly_licence"]["ex_gst"] == 373_200
    assert est["monthly_licence"]["gst"] == round(373_200 * 0.18)
    assert est["annual_licence"]["ex_gst"] == 373_200 * 12
    assert est["technical_pilot"]["ex_gst"] == 250_000
    assert est["one_time_implementation"]["ex_gst"] == 600_000
    assert est["one_time_total"]["ex_gst"] == 850_000
    assert est["first_year_total"]["ex_gst"] == 850_000 + 373_200 * 12
    assert est["second_year_software_total"]["ex_gst"] == 373_200 * 12
    assert est["pilot_adjustment"]["amount_ex_gst"] == 0
    assert "PRELIMINARY" in est["status"]
    assert "quoted after benchmarking" in est["hardware"]


def test_pilot_credit_reduces_one_time_total():
    est = commercial_estimate(10, {"pilot_credit_on_production": 100_000})
    assert est["pilot_adjustment"]["amount_ex_gst"] == -100_000
    assert est["one_time_total"]["ex_gst"] == 250_000 + 600_000 - 100_000


def test_estimate_without_pilot():
    est = commercial_estimate(10, include_pilot=False)
    assert est["technical_pilot"]["ex_gst"] == 0
    assert est["one_time_total"]["ex_gst"] == 600_000


def test_editable_pricing_config_is_validated():
    cfg = validate_pricing({"technical_pilot_fee": 300_000, "gst_rate": 0.12})
    assert cfg["technical_pilot_fee"] == 300_000 and cfg["gst_rate"] == 0.12
    with pytest.raises(ValueError):
        validate_pricing({"licence_tiers": [{"label": "a", "up_to": None, "rate_per_camera_month": 1},
                                             {"label": "b", "up_to": 10, "rate_per_camera_month": 1}]})
    with pytest.raises(ValueError):
        validate_pricing({"licence_tiers": [{"label": "a", "up_to": 50, "rate_per_camera_month": 1},
                                             {"label": "b", "up_to": 40, "rate_per_camera_month": 1}]})

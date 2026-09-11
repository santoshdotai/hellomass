import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.main import app
from backend.solution_designer.catalog import GPU_CAPACITY_DISCLAIMER
from backend.solution_designer.csv_io import parse_csv, template_csv, to_csv
from backend.solution_designer.engine import run_assessment
from backend.solution_designer.report import SECTIONS, render_html, report_sections
from backend.solution_designer.sample import sample_request
from backend.solution_designer.schemas import AssessmentRequest, CameraSpec


# ---------------------------------------------------------------- missing-field handling
def test_missing_fields_default_to_unknown_not_values():
    c = CameraSpec(name="x")
    for f in ("resolution", "fps", "codec", "rtsp_available", "view_type", "lighting"):
        assert getattr(c, f) is None


def test_validation_rejects_bad_values():
    with pytest.raises(ValidationError):
        CameraSpec(name="x", fps=25000)
    with pytest.raises(ValidationError):
        CameraSpec(name="x", resolution="8k-ish")
    with pytest.raises(ValidationError):
        CameraSpec(name="x", use_cases=["face_recognition"])
    with pytest.raises(ValidationError):
        AssessmentRequest(client={"company_name": "A"}, site={"name": "S"}, cameras=[], requirements={"use_cases": ["occupancy"]})
    with pytest.raises(ValidationError):  # inventory exceeds declared count
        AssessmentRequest(client={"company_name": "A"}, site={"name": "S", "existing_camera_count": 5},
                          cameras=[{"name": "g", "count": 10}], requirements={"use_cases": ["occupancy"]})
    with pytest.raises(ValidationError):  # at least one use case
        AssessmentRequest(client={"company_name": "A"}, site={"name": "S", "existing_camera_count": 5},
                          requirements={"use_cases": []})


def test_count_only_site_expands_to_unspecified_group_with_validation():
    req = AssessmentRequest(client={"company_name": "A"}, site={"name": "S", "existing_camera_count": 25},
                            requirements={"use_cases": ["occupancy"]})
    a = run_assessment(req)
    assert a["suitability_summary"]["total_cameras"] == 25
    assert a["suitability"][0]["label"].startswith("Cameras with no specification")
    assert a["suitability"][0]["validation_items"]
    assert a["calculations"]["total_stream_bandwidth_mbps"]["value"] is None  # no bitrate, no assumption
    assert a["decision"]["recommendation"] == "TECHNICAL PILOT FIRST"


# ---------------------------------------------------------------- sample assessment (348 cameras)
@pytest.fixture(scope="module")
def sample_result():
    return run_assessment(sample_request())


def test_sample_recommends_pilot_and_no_final_hardware(sample_result):
    a = sample_result
    assert a["suitability_summary"]["total_cameras"] == 348
    assert a["input"]["site"]["employees"] == 1000
    assert a["decision"]["recommendation"] == "TECHNICAL PILOT FIRST"
    assert a["decision"]["final_hardware_recommended"] is False
    assert a["compute"]["capacity_statement"] == GPU_CAPACITY_DISCLAIMER
    assert a["compute"]["final_hardware_can_be_recommended"] is False
    assert a["pilot"]["duration_days"] == 30
    assert 8 <= a["pilot"]["camera_count"] <= 12
    assert len(a["pilot"]["areas"]) == 2
    assert 2 <= len(a["pilot"]["use_cases"]) <= 3
    assert {u["id"] for u in a["pilot"]["use_cases"]} <= {"restricted_zone", "occupancy", "ppe"}


def test_sample_never_counts_unsuitable_cameras_in_licence(sample_result):
    a = sample_result
    assert a["commercial"]["active_ai_cameras"] == a["suitability_summary"]["candidate_ai_cameras"]
    assert a["commercial"]["active_ai_cameras"] < 348
    assert a["commercial_scenario_all_cameras"]["active_cameras"] == 348


def test_sample_flags_nvr_and_gpu_unknowns_in_risks_and_actions(sample_result):
    titles = " ".join(r["title"] for r in sample_result["risks"])
    assert "NVR/VMS stream export capability unknown" in titles
    assert "GPU model unknown" in titles
    assert "analog camera" in titles
    actions = " ".join(sample_result["required_client_actions"])
    assert "nvidia-smi" in actions
    assert "HR and legal approval" in actions  # PPE selected


def test_sample_calculations_are_traceable(sample_result):
    calcs = sample_result["calculations"]
    bw = calcs["total_stream_bandwidth_mbps"]
    assert bw["value"] == round(bw["inputs"]["active_stream_count"] * bw["inputs"]["average_stream_bitrate_mbps"], 2)
    assert any("assumed 3.0 Mbps" in s for s in bw["assumptions"])
    assert calcs["recommended_network_capacity_mbps"]["value"] == round(bw["value"] * 1.5, 2)


def test_sample_privacy_distinguishes_identification(sample_result):
    assert "separately reviewed module" in sample_result["architecture"]["privacy"]
    ppe = next(u for u in sample_result["use_cases"] if u["id"] == "ppe")
    assert ppe["approvals_required"]


# ---------------------------------------------------------------- report generation
def test_report_has_all_17_sections(sample_result):
    secs = report_sections(sample_result)
    assert [s["title"] for s in secs] == SECTIONS and len(SECTIONS) == 17
    html = render_html(sample_result)
    assert "PRELIMINARY" in html
    assert GPU_CAPACITY_DISCLAIMER in html
    # No forbidden guarantee language anywhere in the generated report.
    from backend.solution_designer.narrative import _violates
    assert not _violates(html)
    for t in SECTIONS:
        assert t in html


def test_narrative_is_rule_based_without_api_key(sample_result):
    assert sample_result["narrative_generated_by"] == "rule_based"
    assert "pilot" in sample_result["narrative"]["executive_summary"].lower()


# ---------------------------------------------------------------- CSV
def test_csv_roundtrip_and_error_rows():
    cams, errs = parse_csv(template_csv())
    assert len(cams) == 1 and not errs
    assert cams[0].rtsp_available is True and cams[0].use_cases == ["restricted_zone", "ppe"]
    bad = "name,count,fps,rtsp_available\nok,2,15,yes\nbad,1,99999,maybe\n"
    cams, errs = parse_csv(bad)
    assert len(cams) == 1 and errs[0]["row"] == 3
    out = to_csv([c.model_dump() for c in cams])
    assert "yes" in out and "ok" in out


# ---------------------------------------------------------------- API + persistence
def test_api_create_get_report_and_pricing():
    with TestClient(app) as client:
        r = client.get("/api/designer/catalog")
        assert r.status_code == 200 and len(r.json()["use_cases"]) == 11
        payload = json.loads(sample_request().model_dump_json())
        r = client.post("/api/designer/assessments", json=payload)
        assert r.status_code == 200, r.text
        aid = r.json()["id"]
        r = client.get(f"/api/designer/assessments/{aid}")
        assert r.status_code == 200 and r.json()["suitability_summary"]["total_cameras"] == 348
        assert r.json()["commercial"]["monthly_licence"]["ex_gst"] > 0
        r = client.get(f"/api/designer/assessments/{aid}/report")
        assert r.status_code == 200 and "Executive summary" in r.text
        r = client.get(f"/api/designer/assessments/{aid}/report?format=docx")
        assert r.status_code in (200, 501)
        r = client.get("/api/designer/assessments")
        assert any(x["id"] == aid for x in r.json()["assessments"])
        site_id = client.get(f"/api/designer/assessments/{aid}").json()["site"]["id"]
        r = client.get(f"/api/designer/sites/{site_id}/cameras.csv")
        assert r.status_code == 200 and "Assembly hall domes" in r.text
        # pricing config round trip
        r = client.put("/api/designer/pricing", json={"technical_pilot_fee": 300000})
        assert r.status_code == 200 and r.json()["pricing"]["technical_pilot_fee"] == 300000
        r = client.get("/api/designer/pricing/estimate?active_cameras=60")
        assert r.json()["technical_pilot"]["ex_gst"] == 300000
        assert r.json()["monthly_licence"]["ex_gst"] == 50 * 1500 + 10 * 1200
        client.post("/api/designer/pricing/reset")
        r = client.post("/api/designer/cameras/import", files={"file": ("c.csv", template_csv().encode(), "text/csv")})
        assert r.json()["imported"] == 1
        r = client.post("/api/designer/assessments/preview", json={"client": {"company_name": "x"}, "site": {"name": "s"},
                                                                    "requirements": {"use_cases": ["occupancy"]}})
        assert r.status_code == 422


def test_forbidden_claim_check_is_sentence_aware():
    from backend.solution_designer.narrative import _violates
    assert not _violates("No video-analytics system achieves 100% accuracy; targets are measured in the pilot.")
    assert _violates("Our system achieves 100% accuracy on all cameras.")
    assert _violates("One T4 GPU can easily handle 348 cameras.")
    assert not _violates("Final GPU capacity cannot be guaranteed without benchmarking representative client streams.")

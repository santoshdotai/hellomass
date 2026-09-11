from backend.solution_designer.suitability import score_camera, summarise, WEIGHTS
from backend.solution_designer.catalog import SITE_VALIDATION

GOOD = {
    "name": "Good dome", "count": 1, "camera_type": "ip_fixed", "resolution": "1080p", "fps": 15, "codec": "h264",
    "rtsp_available": True, "onvif_available": True, "substream_available": True, "is_ptz": False,
    "view_type": "oblique", "lighting": "good", "occlusion": "none", "motion_blur": "none",
    "stream_stability": "stable", "subject_height_px": 150,
}
NVR_OK = {"rtsp_available": True, "api_sdk_available": True}
NVR_NONE = {"rtsp_available": False, "api_sdk_available": False}


def test_weights_sum_to_100():
    assert sum(WEIGHTS.values()) == 100


def test_fully_specified_good_camera_is_class_a_with_reasons():
    r = score_camera(GOOD, NVR_OK, ["restricted_zone", "ppe"])
    assert r.classification == "A" and r.score >= 80
    assert not r.hard_blockers and not r.validation_items
    assert len(r.factors) == 12 and all(f.reason for f in r.factors)


def test_missing_fields_are_not_invented_and_flagged():
    r = score_camera({"name": "Mystery", "count": 5}, None, ["occupancy"])
    assert r.classification in ("C", "D")
    assert r.score < 60
    assert any(SITE_VALIDATION in v for v in r.validation_items)
    assert all(f.validation_required for f in r.factors if f.factor != "use_case_fit")


def test_unknown_stream_caps_class_at_b():
    cam = dict(GOOD, rtsp_available=None, onvif_available=None, substream_available=None)
    r = score_camera(cam, None, ["occupancy"])
    assert r.classification != "A"
    assert any("Class capped at B" in v or SITE_VALIDATION in v for v in r.validation_items)


def test_nvr_without_rtsp_or_api_and_no_camera_rtsp_is_class_d():
    cam = dict(GOOD, rtsp_available=False)
    r = score_camera(cam, NVR_NONE, ["occupancy"])
    assert r.classification == "D"
    assert r.hard_blockers and "no obtainable video stream" in r.hard_blockers[0].lower()


def test_nvr_without_rtsp_but_camera_rtsp_direct_is_fine():
    r = score_camera(GOOD, NVR_NONE, ["occupancy"])
    assert r.classification == "A"


def test_analog_camera_through_dvr_without_rtsp_is_unsuitable():
    cam = {"name": "Analog", "count": 80, "camera_type": "analog_dvr", "resolution": "d1"}
    r = score_camera(cam, NVR_NONE, ["occupancy"])
    assert r.classification == "D"
    assert "analog" in r.hard_blockers[0].lower()
    assert any("Replace the DVR" in a or "new IP camera" in a for a in r.required_actions)


def test_analog_camera_through_dvr_with_rtsp_needs_validation():
    cam = {"name": "Analog", "count": 80, "camera_type": "analog_dvr", "resolution": "d1", "fps": 12, "codec": "h264"}
    r = score_camera(cam, NVR_OK, ["occupancy"])
    assert not r.hard_blockers
    assert r.classification in ("C", "D")
    assert any("DVR" in f.reason for f in r.factors if f.factor == "stream_accessibility")
    assert any("Upgrade" in a for a in r.required_actions)  # D1 resolution


def test_overhead_view_penalised_for_ppe():
    cam = dict(GOOD, view_type="overhead")
    r = score_camera(cam, NVR_OK, ["ppe"])
    angle = next(f for f in r.factors if f.factor == "camera_angle")
    assert angle.points < WEIGHTS["camera_angle"]
    assert angle.action and "oblique" in angle.action
    assert r.use_case_notes["ppe"]["fit"] is False


def test_ptz_camera_flagged_and_excluded_from_tampering():
    cam = dict(GOOD, camera_type="ip_ptz", is_ptz=True)
    r = score_camera(cam, NVR_OK, ["camera_tampering"])
    assert any("PTZ" in f.reason for f in r.factors if f.factor == "mount")
    assert r.use_case_notes["camera_tampering"]["fit"] is False


def test_small_subject_requires_new_placement():
    cam = dict(GOOD, subject_height_px=40)
    r = score_camera(cam, NVR_OK, ["ppe"])
    sub = next(f for f in r.factors if f.factor == "subject_size")
    assert sub.action and ("placement" in sub.action.lower() or "reposition" in sub.action.lower())


def test_summary_counts_cameras_by_class():
    rs = [score_camera(dict(GOOD, count=10), NVR_OK, ["occupancy"]),
          score_camera({"name": "Analog", "count": 5, "camera_type": "analog_dvr"}, NVR_NONE, ["occupancy"])]
    s = summarise(rs)
    assert s["total_cameras"] == 15
    assert s["by_class"]["A"]["cameras"] == 10 and s["by_class"]["D"]["cameras"] == 5
    assert s["candidate_ai_cameras"] == 10

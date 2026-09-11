
from src.utils.config import apply_env_overrides, deep_merge, load_config
from src.utils.time_utils import format_hms, is_within_business_hours, parse_iso, utc_iso
from datetime import datetime, timezone


def test_default_config_loads_and_env_overrides(tmp_path):
    cfg = load_config(env={"SOUVENO_MODEL__CONFIDENCE": "0.55", "SOUVENO_APP__PORT": "9000", "SOUVENO_WEBHOOK__ENABLED": "true",
                           "SOUVENO_SOURCE__RTSP__STREAM_PROFILE": "sub", "SOUVENO_BUSINESS_HOURS__DAYS": "[0,1]"}, load_dotenv=False)
    assert cfg.model.confidence == 0.55 and cfg.app.port == 9000 and cfg.webhook.enabled is True
    assert cfg.source.rtsp.stream_profile == "sub" and cfg.business_hours.days == [0, 1]
    assert "restricted_zone_intrusion" in cfg.rules.to_dict()


def test_local_yaml_overrides_default(tmp_path):
    local = tmp_path / "local.yaml"
    local.write_text("app:\n  port: 7777\nmodel:\n  device: cpu\n")
    cfg = load_config(local_path=local, env={}, load_dotenv=False)
    assert cfg.app.port == 7777 and cfg.model.device == "cpu" and cfg.model.confidence == 0.4


def test_deep_merge_and_unknown_env_ignored():
    assert deep_merge({"a": {"b": 1, "c": 2}}, {"a": {"b": 5}}) == {"a": {"b": 5, "c": 2}}
    assert apply_env_overrides({"a": {"b": 1}}, {"SOUVENO_ZZ__Y": "1", "OTHER": "x"}) == {"a": {"b": 1}}


def test_business_hours_including_overnight():
    wed_noon = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
    wed_night = datetime(2026, 9, 9, 23, 30, tzinfo=timezone.utc)
    sun_noon = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
    assert is_within_business_hours(wed_noon, "08:00", "18:00", [0, 1, 2, 3, 4], "UTC")
    assert not is_within_business_hours(wed_night, "08:00", "18:00", [0, 1, 2, 3, 4], "UTC")
    assert not is_within_business_hours(sun_noon, "08:00", "18:00", [0, 1, 2, 3, 4], "UTC")
    assert is_within_business_hours(wed_night, "22:00", "06:00", [2], "UTC")          # night shift starting Wednesday
    thu_early = datetime(2026, 9, 10, 3, 0, tzinfo=timezone.utc)
    assert is_within_business_hours(thu_early, "22:00", "06:00", [2], "UTC")


def test_time_helpers():
    iso = utc_iso(datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc))
    assert iso == "2026-01-02T03:04:05Z" and parse_iso(iso).hour == 3
    assert format_hms(3661) == "01:01:01"

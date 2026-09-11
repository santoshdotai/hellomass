import json

import pytest

from src.storage.database import Database
from src.storage.migrations import LATEST_VERSION
from src.storage.repositories import Repositories


@pytest.fixture()
def repos(tmp_path):
    db = Database(tmp_path / "t.db").connect()
    yield Repositories(db)
    db.close()


def _event(i, **kw):
    e = {"event_id": f"EV-{i}", "event_type": "restricted_zone_intrusion", "title": f"t{i}", "rule_id": "R", "source_id": "cam1",
         "source_name": "Cam 1", "zone_id": "Z", "zone_name": "Bay", "track_id": i, "timestamp": f"2026-09-0{1 + i % 5}T10:00:00Z",
         "media_time": None, "severity": "high", "confidence": 0.9, "snapshot_path": None, "clip_path": None, "status": "new",
         "acknowledged_by": None, "acknowledged_at": None, "notes": "", "metadata": {"k": i}}
    e.update(kw)
    return e


def test_migrations_and_status(repos):
    st = repos.db.status()
    assert st["ok"] and st["schema_version"] == LATEST_VERSION
    tables = {r[0] for r in repos.db.query("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"sources", "zones", "rules", "events", "acknowledgements", "application_settings", "health_logs"} <= tables
    idx = {r[0] for r in repos.db.query("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_events_timestamp" in idx and "idx_events_status" in idx


def test_reopen_existing_database_is_idempotent(tmp_path):
    p = tmp_path / "x.db"
    Database(p).connect().close()
    db = Database(p).connect()
    assert db.version == LATEST_VERSION
    db.close()


def test_corrupt_database_is_moved_aside_and_recreated(tmp_path):
    p = tmp_path / "bad.db"
    p.write_bytes(b"this is not a sqlite file" * 100)
    db = Database(p).connect()
    assert db.status()["ok"] and db.recovered
    assert list(tmp_path.glob("bad.corrupt-*.db"))
    db.close()


def test_sources_never_store_credentials(repos):
    repos.sources.upsert("rtsp-1", "Gate", "rtsp", "rtsp://***:***@h/x", {"type": "rtsp", "url": "rtsp://u:p@h/x", "username": "u", "password": "p", "transport": "tcp"})
    row = repos.sources.get("rtsp-1")
    raw = json.dumps(row)
    assert "u:p" not in raw and '"password"' not in raw and row["spec"]["transport"] == "tcp"


def test_zones_roundtrip(repos):
    saved = repos.zones.replace_for_source("cam1", [{"zone_id": "Z1", "name": "Bay", "kind": "restricted", "points": [[0, 0], [1, 0], [1, 1]],
                                                    "color": "#f00", "dwell_threshold_seconds": 12, "direction_flipped": True}])
    assert saved[0]["points"] == [[0, 0], [1, 0], [1, 1]] and saved[0]["direction_flipped"] is True
    repos.zones.replace_for_source("cam1", [])
    assert repos.zones.list_for_source("cam1") == []


def test_rules_upsert(repos):
    repos.rules.upsert_many([{"rule_id": "R1", "rule_type": "dwell_time_exceeded", "name": "d", "threshold": 10, "schedule": {"mode": "always"}}])
    repos.rules.upsert_many([{"rule_id": "R1", "rule_type": "dwell_time_exceeded", "name": "d", "threshold": 20, "schedule": {"mode": "always"}}])
    rules = repos.rules.list()
    assert len(rules) == 1 and rules[0]["threshold"] == 20 and rules[0]["schedule"] == {"mode": "always"}


def test_events_insert_filter_count_and_status(repos):
    for i in range(6):
        repos.events.insert(_event(i, severity="high" if i % 2 else "low"))
    assert repos.events.count() == 6
    assert repos.events.count({"severity": "high"}) == 3
    assert repos.events.count({"date_from": "2026-09-03T00:00:00Z"}) == 3  # days 3,4,5 -> i=2,3,4 ... plus duplicates
    hi = repos.events.list({"severity": "high", "source_id": "cam1"}, limit=2)
    assert len(hi) == 2 and hi[0]["metadata"] == {"k": 3}  # newest timestamp first (i=3 -> 2026-09-04)
    updated = repos.events.set_status("EV-1", "acknowledged", "santosh", "checked")
    assert updated["status"] == "acknowledged" and updated["acknowledged_by"] == "santosh" and updated["acknowledged_at"]
    assert repos.events.count_by("status")["acknowledged"] == 1
    repos.acks.add("EV-1", "acknowledged", "santosh", "checked")
    assert repos.acks.for_event("EV-1")[0]["actor"] == "santosh"


def test_event_paths_and_csv_export(repos):
    repos.events.insert(_event(1))
    repos.events.update_paths("EV-1", snapshot_path="/tmp/a.jpg", clip_path="/tmp/a.mp4")
    e = repos.events.get("EV-1")
    assert e["snapshot_path"] == "/tmp/a.jpg" and e["clip_path"] == "/tmp/a.mp4"
    csv_text = repos.events.export_csv()
    lines = csv_text.strip().splitlines()
    assert lines[0].startswith("event_id,timestamp,event_type,title,severity,status")
    assert len(lines) == 2 and "EV-1" in lines[1]


def test_settings_and_health_logs(repos):
    repos.settings.set("runtime", {"confidence": 0.5})
    repos.settings.set("runtime", {"confidence": 0.6})
    assert repos.settings.get("runtime")["confidence"] == 0.6 and repos.settings.get("missing", 1) == 1
    repos.health.add({"source_id": "cam1", "source_status": "live", "capture_fps": 10, "details": {"password": "x"}})
    rows = repos.health.recent()
    assert rows[0]["capture_fps"] == 10 and "x" not in rows[0]["details_json"]


def test_parameterised_queries_resist_injection(repos):
    repos.events.insert(_event(1))
    assert repos.events.list({"search": "' OR 1=1 --"}) == []
    assert repos.events.count({"severity": "high' OR '1'='1"}) == 0
    with pytest.raises(ValueError):
        repos.events.count_by("title; DROP TABLE events")

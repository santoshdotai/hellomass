import time

import pytest
from fastapi.testclient import TestClient

from src.ui.dashboard import create_app


@pytest.fixture()
def client(tmp_path):
    overrides = {"database": {"path": str(tmp_path / "api.db")}, "evidence": {"directory": str(tmp_path / "evidence")},
                 "logging": {"directory": str(tmp_path / "logs")}, "model": {"backend": "groundtruth"},
                 "app": {"autostart_source": False}}
    app = create_app(overrides=overrides, mount_legacy=False)
    with TestClient(app) as c:
        yield c


def test_dashboard_and_health(client):
    assert client.get("/").status_code == 200 and "SOUVENO AI" in client.get("/").text
    h = client.get("/api/vi/health").json()
    assert h["status"] == "ok" and h["database"]["ok"] and "anonymous" in h["privacy"]
    assert client.get("/assets/js/app.js").status_code == 200
    fav = client.get("/favicon.ico")
    assert fav.status_code == 204 and fav.content == b""   # a 204 must carry no body (uvicorn enforces it)


def test_source_lifecycle_zones_events_ack_csv(client):
    r = client.post("/api/vi/source/start", json={"type": "synthetic", "fps": 15})
    assert r.status_code == 200 and r.json()["state"]["source"]["kind"] == "synthetic"
    deadline = time.time() + 40
    while time.time() < deadline:
        ev = client.get("/api/vi/events").json()
        if ev["total"] >= 2 and any(e["event_type"] == "restricted_zone_intrusion" for e in ev["events"]):
            break
        time.sleep(0.5)
    ev = client.get("/api/vi/events?event_type=restricted_zone_intrusion").json()
    assert ev["total"] >= 1
    e = ev["events"][0]
    assert e["has_snapshot"] and "snapshot_path" not in e
    assert client.get(e["snapshot_url"]).headers["content-type"] == "image/jpeg"
    st = client.get("/api/vi/state").json()
    assert st["running"] and st["counts"]["people"] >= 0 and st["privacy"]
    assert client.get("/api/vi/snapshot.jpg").headers["content-type"] == "image/jpeg"
    # acknowledge -> database
    r = client.post(f"/api/vi/events/{e['event_id']}/ack", json={"actor": "presenter", "note": "ok"})
    assert r.json()["event"]["status"] == "acknowledged"
    assert client.get(f"/api/vi/events/{e['event_id']}").json()["audit"][0]["actor"] == "presenter"
    assert client.get("/api/vi/events?status=acknowledged").json()["total"] == 1
    csv = client.get("/api/vi/events/export.csv?status=acknowledged")
    assert csv.headers["content-type"].startswith("text/csv") and e["event_id"] in csv.text
    # zones: invalid rejected, valid saved
    bad = client.put("/api/vi/zones", json={"zones": [{"name": "X", "kind": "restricted", "points": [[0, 0], [1, 1]]}]})
    assert bad.status_code == 422
    good = client.put("/api/vi/zones", json={"zones": [{"name": "Bay", "kind": "restricted", "points": [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5]]}]})
    assert good.status_code == 200 and client.get("/api/vi/zones").json()["zones"][0]["name"] == "Bay"
    # demo helpers
    assert client.post("/api/vi/demo/reset-counts").json()["ok"]
    assert client.post("/api/vi/demo/verify-dwell", json={"seconds": 3}).json()["threshold_seconds"] == 3
    assert client.post("/api/vi/demo/enable-restricted").json()["ok"]
    assert client.post("/api/vi/demo/test-event").json()["event"]["metadata"]["test"]
    # settings & rules
    s = client.put("/api/vi/settings", json={"confidence": 0.6, "analytics_fps": 5}).json()["settings"]
    assert s["confidence"] == 0.6 and client.get("/api/vi/settings").json()["settings"]["analytics_fps"] == 5
    rules = client.get("/api/vi/rules").json()["rules"]
    rid = next(r["rule_id"] for r in rules if r["rule_type"] == "line_crossed_in")
    upd = client.put("/api/vi/rules", json={"rules": [{"rule_id": rid, "enabled": False, "severity": "high"}]}).json()["rules"]
    assert next(r for r in upd if r["rule_id"] == rid)["enabled"] is False
    assert client.post("/api/vi/source/stop").json()["ok"]
    assert client.get("/api/vi/state").json()["running"] is False


def test_bad_source_returns_friendly_400(client):
    r = client.post("/api/vi/source/start", json={"type": "file", "path": "nope.mp4"})
    assert r.status_code == 400 and "not found" in r.json()["detail"]
    r = client.post("/api/vi/source/start", json={"type": "onvif"})
    assert r.status_code == 400 and "ONVIF" in r.json()["detail"]
    assert client.get("/api/vi/events/EV-NOPE/snapshot").status_code == 404


def test_audit_endpoint_runs_and_classifies(client):
    r = client.post("/api/vi/audit", json={"spec": {"type": "synthetic"}, "duration_seconds": 3})
    aid = r.json()["audit_id"]
    deadline = time.time() + 15
    while time.time() < deadline:
        a = client.get(f"/api/vi/audit/{aid}").json()
        if a["status"] == "done":
            break
        time.sleep(0.5)
    assert a["status"] == "done" and a["reachable"] and a["classification"] in "ABCD" and a["resolution"] == "960x540"
    bad = client.post("/api/vi/audit", json={"spec": {"type": "rtsp", "url": "rtsp://user:pw@127.0.0.1:1/x"}, "duration_seconds": 3}).json()
    deadline = time.time() + 30
    while time.time() < deadline:
        b = client.get(f"/api/vi/audit/{bad['audit_id']}").json()
        if b["status"] == "done":
            break
        time.sleep(0.5)
    assert b["classification"] == "D" and "pw" not in b["masked_url"] and "***" in b["masked_url"]

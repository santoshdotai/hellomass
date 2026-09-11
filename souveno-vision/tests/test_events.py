import time

import numpy as np
import pytest

from src.events.evidence import EvidenceManager
from src.events.service import EventService
from src.events.webhook import WebhookDispatcher
from src.rules.models import EventCandidate, Rule, RuleType, Severity
from src.storage.database import Database
from src.storage.repositories import Repositories


@pytest.fixture()
def service(tmp_path):
    db = Database(tmp_path / "e.db").connect()
    repos = Repositories(db)
    evidence = EvidenceManager(tmp_path / "evidence", pre_seconds=1, post_seconds=0.2, fps=5, max_clips_per_minute=2)
    svc = EventService(repos, evidence, WebhookDispatcher(enabled=False))
    yield svc, repos, evidence
    db.close()


def candidate(rule_type=RuleType.RESTRICTED_ZONE_INTRUSION, evidence=True, notify=False, ts=None, **meta):
    rule = Rule(rule_type=rule_type, severity=Severity.HIGH, evidence_required=evidence, notify=notify)
    return EventCandidate(rule, rule_type.value, "Person 4 entered restricted zone 'Bay'", ts or time.time(), Severity.HIGH,
                          "cam1", "Cam 1", "Z1", "Bay", 4, 0.91, dict(meta))


def frame():
    return np.zeros((240, 320, 3), dtype=np.uint8)


def test_event_creation_persists_snapshot_and_fields(service):
    svc, repos, evidence = service
    ev = svc.create(candidate(extra="x"), frame())
    assert ev["event_id"].startswith("EV-") and ev["status"] == "new" and ev["severity"] == "high"
    assert ev["source_name"] == "Cam 1" and ev["zone_name"] == "Bay" and ev["track_id"] == 4 and ev["confidence"] == 0.91
    assert ev["timestamp"].endswith("Z") and ev["metadata"]["extra"] == "x" and ev["metadata"]["rule_name"]
    assert ev["snapshot_path"] and (evidence.snapshots_dir / ev["snapshot_path"].split("/")[-1]).exists()
    assert repos.events.get(ev["event_id"])["title"] == ev["title"]
    assert svc.recent()[0]["event_id"] == ev["event_id"]


def test_no_evidence_when_not_required(service):
    svc, _, _ = service
    ev = svc.create(candidate(rule_type=RuleType.LINE_CROSSED_IN, evidence=False), frame())
    assert ev["snapshot_path"] is None and ev["clip_path"] is None


def test_acknowledge_resolve_dismiss_with_audit(service):
    svc, repos, _ = service
    ev = svc.create(candidate(evidence=False), None)
    acked = svc.acknowledge(ev["event_id"], "santosh", "checked on site")
    assert acked["status"] == "acknowledged" and acked["acknowledged_by"] == "santosh" and acked["acknowledged_at"]
    assert acked["notes"] == "checked on site"
    resolved = svc.resolve(ev["event_id"], "santosh")
    assert resolved["status"] == "resolved"
    assert svc.dismiss("EV-DOES-NOT-EXIST") is None
    audit = repos.acks.for_event(ev["event_id"])
    assert [a["action"] for a in audit] == ["acknowledged", "resolved"] and audit[0]["note"] == "checked on site"
    assert svc.recent()[0]["status"] == "resolved"


def test_stats_and_csv(service):
    svc, _, _ = service
    svc.create(candidate(evidence=False), None)
    svc.create(candidate(rule_type=RuleType.DWELL_TIME_EXCEEDED, evidence=False), None)
    stats = svc.stats_today()
    assert stats["total_today"] == 2 and stats["restricted_violations_today"] == 1 and stats["active_alerts"] == 2
    csv_text = svc.export_csv({"event_type": "dwell_time_exceeded"})
    assert csv_text.count("\n") == 2 and "dwell_time_exceeded" in csv_text


def test_clip_recording_with_pre_buffer_and_rate_limit(service):
    svc, repos, evidence = service
    for i in range(6):
        evidence.push_frame(frame(), time.time())
    ev1 = svc.create(candidate(), frame())
    ev2 = svc.create(candidate(), frame())
    ev3 = svc.create(candidate(), frame())  # third clip within a minute -> skipped
    assert ev1["metadata"].get("clip_pending") and ev2["metadata"].get("clip_pending")
    assert not ev3["metadata"].get("clip_pending") and evidence.clips_skipped == 1
    deadline = time.time() + 5
    while time.time() < deadline:
        evidence.push_frame(frame(), time.time())
        time.sleep(0.05)
        if repos.events.get(ev1["event_id"])["clip_path"] and repos.events.get(ev2["event_id"])["clip_path"]:
            break
    assert repos.events.get(ev1["event_id"])["clip_path"].endswith((".mp4", ".avi"))
    assert svc.recent()[2]["clip_path"]  # feed entry updated in place


def test_retention_cleanup_removes_old_files(service, tmp_path):
    svc, repos, evidence = service
    ev = svc.create(candidate(), frame())
    import os
    old = time.time() - 40 * 86400
    os.utime(ev["snapshot_path"], (old, old))
    result = evidence.cleanup()
    assert result["removed"] >= 1
    # database purge
    svc.repos.events.insert({**repos.events.get(ev["event_id"]), "event_id": "EV-OLD", "timestamp": "2020-01-01T00:00:00Z",
                             "metadata": {}, "snapshot_path": None, "clip_path": None})
    assert svc.purge_older_than(30) == 1


def test_webhook_payload_has_no_paths_and_marks_privacy(service):
    svc, _, _ = service
    ev = svc.create(candidate(), frame())
    payload = EventService.to_webhook_payload(ev)
    assert "snapshot_path" not in payload["event"] and payload["evidence"]["snapshot"] is True
    assert "anonymous" in payload["privacy"]

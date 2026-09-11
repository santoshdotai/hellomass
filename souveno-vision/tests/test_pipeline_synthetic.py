"""Deterministic end-to-end test: synthetic scene -> ground-truth detector -> tracker ->
zones/lines -> rules -> events with snapshots, verified through the real pipeline object."""
import time
from pathlib import Path

import pytest

from src.events.evidence import EvidenceManager
from src.events.service import EventService
from src.monitoring.health import HealthMonitor
from src.pipeline import VisionPipeline
from src.storage.database import Database
from src.storage.repositories import Repositories
from src.utils.config import load_config


@pytest.fixture()
def pipeline(tmp_path):
    cfg = load_config(env={}, load_dotenv=False)
    db = Database(tmp_path / "p.db").connect()
    repos = Repositories(db)
    evidence = EvidenceManager(tmp_path / "evidence", pre_seconds=1, post_seconds=1, fps=10)
    events = EventService(repos, evidence)
    p = VisionPipeline(cfg, repos, events, evidence, HealthMonitor(tmp_path), base_dir=Path.cwd())
    p.apply_settings({"model_backend": "groundtruth", "analytics_fps": 10, "dwell_threshold_seconds": 6,
                      "business_hours": {"start": "00:00", "end": "23:59", "days": [0, 1, 2, 3, 4, 5, 6]}}, persist=False)
    yield p, repos, evidence
    p.shutdown()
    db.close()


def _wait(pred, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return True
        time.sleep(0.2)
    return False


def test_synthetic_scene_produces_counts_events_and_evidence(pipeline):
    p, repos, evidence = pipeline
    st = p.start({"type": "synthetic", "fps": 15, "realtime": True})
    assert st["source"]["status"] in ("connecting", "live")
    assert len(p.zones) == 3  # default synthetic layout: restricted, occupancy, line
    assert _wait(lambda: p.state()["running"] and p.state()["source"]["status"] == "live" and p.state()["counts"]["people"] > 0, 15)
    types = lambda: {e["event_type"] for e in repos.events.list()}
    assert _wait(lambda: {"restricted_zone_intrusion", "dwell_time_exceeded", "line_crossed_in", "line_crossed_out"} <= types(), 60), types()
    st = p.state()
    assert st["counts"]["entries"] >= 1 and st["counts"]["exits"] >= 1 and st["ai"]["backend"] == "ground-truth"
    assert all(t["label"].startswith("Person ") for t in st["tracks"])
    intrusion = next(e for e in repos.events.list() if e["event_type"] == "restricted_zone_intrusion")
    assert intrusion["zone_name"] == "Restricted Bay" and intrusion["track_id"] is not None and intrusion["snapshot_path"]
    assert Path(intrusion["snapshot_path"]).exists()
    assert len(p.latest_jpeg()) > 1000 and len(p.snapshot_jpeg()) > 1000
    dwell = next(e for e in repos.events.list() if e["event_type"] == "dwell_time_exceeded")
    assert dwell["metadata"]["threshold_seconds"] == 8  # the synthetic "Restricted Bay" zone overrides the 6 s default
    # acknowledgement updates the database
    acked = p.events.acknowledge(intrusion["event_id"], "tester", "seen")
    assert repos.events.get(intrusion["event_id"])["status"] == "acknowledged" and acked["acknowledged_by"] == "tester"
    csv_text = p.events.export_csv()
    assert intrusion["event_id"] in csv_text
    # reset counts
    p.reset_counts()
    assert _wait(lambda: p.state()["counts"]["entries"] <= 1, 5)
    health = p.health.snapshot()
    assert health["inference_fps"] > 3 and health["components"]["detector"]["ok"]


def test_zone_save_validation_and_apply(pipeline):
    p, repos, _ = pipeline
    p.start({"type": "synthetic", "fps": 10})
    saved, problems = p.save_zones(p.source_id, [{"name": "Bad", "kind": "restricted", "points": [[0, 0], [1, 1], [1, 0], [0, 1]]}])
    assert problems and "Bad" in problems
    saved, problems = p.save_zones(p.source_id, [{"name": "Gate", "kind": "line", "points": [[0.5, 0.1], [0.5, 0.9]]},
                                                 {"name": "Bay", "kind": "restricted", "points": [[0.6, 0.1], [0.9, 0.1], [0.9, 0.5]], "dwell_threshold_seconds": 3}])
    assert not problems and len(saved) == 2 and [z.name for z in p.zones] == ["Gate", "Bay"]
    assert repos.zones.list_for_source(p.source_id)[1]["dwell_threshold_seconds"] == 3


def test_source_failure_is_reported_not_fatal(pipeline):
    p, _, _ = pipeline
    from src.sources.base import SourceError
    with pytest.raises(SourceError):
        p.start({"type": "file", "path": "does/not/exist.mp4"})
    assert p.state()["running"] is False
    p.start({"type": "synthetic", "fps": 10})
    assert _wait(lambda: p.state()["source"]["status"] == "live", 10)
    p.stop()
    assert p.state()["running"] is False and p.state()["source"]["status"] == "idle"


def test_test_event_and_dwell_verify(pipeline):
    p, repos, _ = pipeline
    ev = p.fire_test_event("dwell_time_exceeded")
    assert ev["metadata"]["test"] is True and ev["event_type"] == "dwell_time_exceeded" and ev["snapshot_path"]
    secs = p.verify_dwell(4)
    assert secs == 4 and p.settings["dwell_threshold_seconds"] == 4
    p._end_dwell_override()
    assert p.settings["dwell_threshold_seconds"] == 6

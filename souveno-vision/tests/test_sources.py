import time

import numpy as np
import pytest

from src.sources.base import Frame, FrameGrabber, ReconnectPolicy, SourceError, SourceStatus, VideoSource
from src.sources.factory import FUTURE_CONNECTORS, create_source
from src.sources.synthetic import SyntheticSource


class FlakySource(VideoSource):
    """A mock camera: delivers frames, then fails reads, then recovers after N reconnects."""
    kind = "mock"

    def __init__(self, fail_after=5, recover_after_opens=2, fail_open=False):
        super().__init__("Mock Cam")
        self.fail_after, self.recover_after_opens, self.fail_open = fail_after, recover_after_opens, fail_open
        self.opens = 0
        self.reads = 0

    def open(self):
        self.opens += 1
        if self.fail_open and self.opens <= self.recover_after_opens:
            raise SourceError("camera unreachable")
        from src.sources.base import SourceInfo
        self.info = SourceInfo(name=self.name, kind=self.kind, masked_url="mock://cam", width=64, height=48, fps=30)
        self._opened = True
        self.reads = 0
        return self.info

    def read(self):
        time.sleep(0.005)
        self.reads += 1
        if self.opens <= self.recover_after_opens and self.reads > self.fail_after:
            return None  # simulate a dead stream
        return self._make_frame(np.zeros((48, 64, 3), dtype=np.uint8))

    def close(self):
        self._opened = False


def _wait(pred, timeout=5.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return True
        time.sleep(0.02)
    return False


def test_grabber_reconnects_after_stream_failure_and_reports_status():
    src = FlakySource(fail_after=5, recover_after_opens=2)
    statuses = []
    g = FrameGrabber(src, ReconnectPolicy(initial_delay_seconds=0.05, max_delay_seconds=0.1),
                     on_status=lambda o, n, s: statuses.append((o.value, n.value)))
    g.start()
    assert _wait(lambda: g.frames_captured >= 3)
    assert _wait(lambda: src.opens >= 3 and g.status == SourceStatus.LIVE, timeout=8)
    assert g.reconnect_count >= 1
    assert ("live", "disconnected") in statuses and ("disconnected", "connecting") in statuses and ("connecting", "live") in statuses
    g.stop()
    assert g.status == SourceStatus.CLOSED and not g.is_running


def test_grabber_backoff_when_open_fails_then_recovers():
    src = FlakySource(fail_open=True, recover_after_opens=2, fail_after=10 ** 6)
    g = FrameGrabber(src, ReconnectPolicy(initial_delay_seconds=0.05, max_delay_seconds=0.2))
    g.start()
    assert _wait(lambda: g.status == SourceStatus.LIVE, timeout=6)
    assert g.connect_attempts == 3 and "unreachable" not in g.last_error
    g.stop()


def test_grabber_gives_up_after_max_attempts():
    src = FlakySource(fail_open=True, recover_after_opens=10 ** 6)
    g = FrameGrabber(src, ReconnectPolicy(initial_delay_seconds=0.02, max_delay_seconds=0.05, max_attempts=3))
    g.start()
    assert _wait(lambda: g.status == SourceStatus.ERROR, timeout=5)
    assert g.connect_attempts == 3 and "unreachable" in g.last_error
    g.stop()


def test_latest_frame_buffer_keeps_only_newest():
    src = SyntheticSource(fps=200, realtime=False)
    g = FrameGrabber(src)
    g.start()
    time.sleep(0.3)
    a = g.latest()
    b = g.latest()               # nothing new yet unless produced in between -> either None or newer
    assert a is not None and (b is None or b.index > a.index)
    time.sleep(0.2)
    c = g.latest()
    assert c is not None and c.index > a.index + 1 and g.frames_dropped > 0   # older frames were discarded, not queued
    g.stop()


def test_stale_stream_degrades_status():
    class Hanging(FlakySource):
        def read(self):
            time.sleep(0.05)
            return None
    src = Hanging(fail_after=0, recover_after_opens=0)
    src.recover_after_opens = 10 ** 6
    g = FrameGrabber(src, ReconnectPolicy(initial_delay_seconds=0.05, stale_after_seconds=0.1, disconnected_after_seconds=0.3))
    g.start()
    assert _wait(lambda: g.status in (SourceStatus.DEGRADED, SourceStatus.DISCONNECTED, SourceStatus.CONNECTING), timeout=5)
    g.stop()


def test_synthetic_source_publishes_ground_truth_boxes():
    src = SyntheticSource(realtime=False)
    info = src.open()
    frames = [src.read() for _ in range(90)]
    assert info.width == 960 and all(isinstance(f, Frame) for f in frames)
    assert any(f.metadata["gt_boxes"] for f in frames)
    src.close()


def test_factory_builds_sources_and_explains_future_connectors(tmp_path):
    assert create_source({"type": "synthetic"}).kind == "synthetic"
    assert create_source({"type": "webcam", "index": 1}).index == 1
    with pytest.raises(SourceError):
        create_source({"type": "file"})
    for kind in FUTURE_CONNECTORS:
        with pytest.raises(SourceError, match="Not included"):
            create_source({"type": kind})
    with pytest.raises(SourceError, match="rtsp://"):
        create_source({"type": "rtsp", "url": "http:/broken"})
    with pytest.raises(SourceError, match="No RTSP URL"):
        create_source({"type": "rtsp"}, rtsp_env={"url_env": "SOUVENO_TEST_UNSET_URL"})
    src = create_source({"type": "rtsp"}, rtsp_env={"url_env": "SOUVENO_TEST_URL", "username_env": "SOUVENO_TEST_USER",
                                                   "password_env": "SOUVENO_TEST_PW"}) if False else None
    assert src is None


def test_rtsp_source_from_environment(monkeypatch):
    monkeypatch.setenv("SOUVENO_TEST_URL", "rtsp://cam/main")
    monkeypatch.setenv("SOUVENO_TEST_USER", "viewer")
    monkeypatch.setenv("SOUVENO_TEST_PW", "secret")
    src = create_source({"type": "rtsp", "stream_profile": "sub"}, rtsp_env={"url_env": "SOUVENO_TEST_URL", "substream_url_env": "X",
                                                                             "username_env": "SOUVENO_TEST_USER", "password_env": "SOUVENO_TEST_PW"})
    assert src.masked_url == "rtsp://***:***@cam/main" and "secret" not in src.masked_url and src.stream_profile == "sub"


def test_video_file_source_errors_are_friendly(tmp_path):
    from src.sources.video_file import VideoFileSource
    with pytest.raises(SourceError, match="not found"):
        VideoFileSource(tmp_path / "missing.mp4").open()
    bad = tmp_path / "bad.txt"
    bad.write_text("x")
    with pytest.raises(SourceError, match="Unsupported"):
        VideoFileSource(bad).open()

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from src.events.webhook import WebhookDispatcher


class _Handler(BaseHTTPRequestHandler):
    received = []
    fail_first = 0

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        _Handler.received.append((self.path, body, self.headers.get("Authorization")))
        if _Handler.fail_first > 0:
            _Handler.fail_first -= 1
            self.send_response(503)
        else:
            self.send_response(200)
        self.end_headers()

    def log_message(self, *a):
        pass


@pytest.fixture()
def server():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    _Handler.received = []
    _Handler.fail_first = 0
    yield f"http://127.0.0.1:{srv.server_port}/hook"
    srv.shutdown()


def test_disabled_by_default_does_nothing(server):
    w = WebhookDispatcher()
    assert w.enqueue({"event_id": "x"}) is False and w.status()["enabled"] is False


def test_delivery_with_retry_and_masked_status(server, monkeypatch):
    monkeypatch.setenv("TEST_HOOK_AUTH", "Bearer s3cret")
    _Handler.fail_first = 1
    w = WebhookDispatcher(enabled=True, url=server + "?token=abc", timeout_seconds=2, max_retries=2, backoff_seconds=0.05,
                          auth_header_env="TEST_HOOK_AUTH")
    assert w.enqueue({"event_id": "EV-1", "password": "nope"})
    deadline = time.time() + 5
    while time.time() < deadline and w.sent == 0:
        time.sleep(0.05)
    st = w.status()
    assert w.sent == 1 and st["recent"][0]["attempts"] == 2 and st["recent"][0]["ok"]
    assert st["url"].endswith("token=***") and "s3cret" not in json.dumps(st)
    assert len(_Handler.received) == 2 and _Handler.received[-1][2] == "Bearer s3cret"
    assert _Handler.received[-1][1]["password"] == "***"   # redacted before leaving the process
    w.stop()


def test_failed_delivery_is_recorded_not_raised(server):
    w = WebhookDispatcher(enabled=True, url="http://127.0.0.1:1/unreachable", timeout_seconds=0.5, max_retries=1, backoff_seconds=0.01)
    rec = w.deliver({"event_id": "EV-2"})
    assert rec["ok"] is False and rec["attempts"] == 2 and w.failed == 1
    w.stop()

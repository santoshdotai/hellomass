"""Layer 10 — optional generic webhook dispatcher (disabled by default).

POSTs each event as JSON from a background thread with timeout, retries and
exponential backoff; never blocks video processing; keeps a delivery log the
Health page can show. Designed to feed n8n, WhatsApp Business API relays,
e-mail gateways, Slack, ERP/HRMS or the Souveno Supabase backend."""
from __future__ import annotations

import json
import os
import queue
import threading
import time
from collections import deque
from typing import Optional

from loguru import logger

from src.security.redaction import mask_url, redact_mapping
from src.utils.time_utils import utc_iso


class WebhookDispatcher:
    def __init__(self, enabled: bool = False, url: str = "", timeout_seconds: float = 5.0, max_retries: int = 3,
                 backoff_seconds: float = 2.0, auth_header_env: str = "", queue_size: int = 200):
        self.enabled = bool(enabled)
        self.url = url or ""
        self.timeout = float(timeout_seconds)
        self.max_retries = int(max_retries)
        self.backoff = float(backoff_seconds)
        self.auth_header_env = auth_header_env or ""
        self._q: queue.Queue = queue.Queue(maxsize=queue_size)
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.deliveries: deque = deque(maxlen=50)
        self.sent = 0
        self.failed = 0
        self.dropped = 0
        self._lock = threading.Lock()

    # ---- config -------------------------------------------------------------------
    def configure(self, enabled: bool, url: str, timeout_seconds: float | None = None, max_retries: int | None = None,
                  backoff_seconds: float | None = None) -> None:
        with self._lock:
            self.enabled, self.url = bool(enabled), url or ""
            if timeout_seconds is not None:
                self.timeout = float(timeout_seconds)
            if max_retries is not None:
                self.max_retries = int(max_retries)
            if backoff_seconds is not None:
                self.backoff = float(backoff_seconds)
        if self.enabled and self.url:
            self.start()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="webhook-dispatcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    # ---- API ---------------------------------------------------------------------------
    def enqueue(self, event: dict) -> bool:
        if not (self.enabled and self.url):
            return False
        self.start()
        try:
            self._q.put_nowait(redact_mapping(event))
            return True
        except queue.Full:
            self.dropped += 1
            logger.warning("Webhook queue full — event dropped (video processing is never blocked)")
            return False

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json", "User-Agent": "SouvenoVisionIntelligence/1.0"}
        auth = os.environ.get(self.auth_header_env, "") if self.auth_header_env else ""
        if auth:
            headers["Authorization"] = auth
        return headers

    def _post_once(self, payload: dict) -> tuple[bool, int | None, str]:
        import requests
        try:
            resp = requests.post(self.url, data=json.dumps(payload, default=str), headers=self._headers(), timeout=self.timeout)
            if 200 <= resp.status_code < 300:
                return True, resp.status_code, ""
            return False, resp.status_code, f"HTTP {resp.status_code}"
        except requests.RequestException as exc:
            return False, None, type(exc).__name__

    def deliver(self, payload: dict) -> dict:
        """Synchronous delivery with retries (used by the worker and by 'Send test')."""
        attempts = 0
        status_code, error, ok = None, "", False
        delay = self.backoff
        while attempts <= self.max_retries and not self._stop.is_set():
            attempts += 1
            ok, status_code, error = self._post_once(payload)
            if ok:
                break
            if attempts <= self.max_retries:
                time.sleep(min(delay, 30))
                delay *= 2
        record = {"event_id": payload.get("event_id", "test"), "ok": ok, "attempts": attempts, "http_status": status_code,
                  "error": error, "at": utc_iso(), "url": mask_url(self.url)}
        with self._lock:
            self.deliveries.appendleft(record)
            if ok:
                self.sent += 1
            else:
                self.failed += 1
        if ok:
            logger.info(f"Webhook delivered {record['event_id']} to {mask_url(self.url)} in {attempts} attempt(s)")
        else:
            logger.warning(f"Webhook delivery failed for {record['event_id']} to {mask_url(self.url)}: {error}")
        return record

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                payload = self._q.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self.deliver(payload)
            except Exception:
                logger.exception("Webhook worker error")

    def status(self) -> dict:
        with self._lock:
            return {"enabled": self.enabled, "url": mask_url(self.url), "configured": bool(self.url), "sent": self.sent,
                    "failed": self.failed, "dropped": self.dropped, "queued": self._q.qsize(),
                    "timeout_seconds": self.timeout, "max_retries": self.max_retries, "backoff_seconds": self.backoff,
                    "recent": list(self.deliveries)[:10]}

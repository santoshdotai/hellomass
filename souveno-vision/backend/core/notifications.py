"""Notification Service abstraction (Stage 6 — WhatsApp alerts).

V0.1 wires up the console implementation only. `WhatsAppNotificationService`
is a real, structurally-complete client for the Meta WhatsApp Cloud API
that simply isn't invoked yet (no access token configured) — switching
NOTIFICATION_PROVIDER=whatsapp and filling in the .env values is the only
change needed to go live, no call-site changes.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from loguru import logger

from config.settings import settings


@dataclass
class AlertMessage:
    title: str
    body: str
    severity: str  # info | warning | critical
    branch: str = "Demo Branch"


class NotificationService(ABC):
    def __init__(self, cooldown_seconds: float = 120.0):
        self.cooldown_seconds = cooldown_seconds
        self._last_sent: dict[str, float] = {}

    def notify(self, alert: AlertMessage, dedupe_key: str) -> bool:
        now = time.time()
        last = self._last_sent.get(dedupe_key, 0)
        if now - last < self.cooldown_seconds:
            return False  # suppressed by cooldown — never spam
        self._last_sent[dedupe_key] = now
        self._send(alert)
        return True

    @abstractmethod
    def _send(self, alert: AlertMessage):
        ...


class ConsoleNotificationService(NotificationService):
    """Default V0.1 implementation — logs to the console/log file."""

    def _send(self, alert: AlertMessage):
        logger.warning(
            f"[SOUVENO VISION ALERT] ({alert.severity.upper()}) {alert.title} — {alert.body} "
            f"[{alert.branch}]"
        )


class WhatsAppNotificationService(NotificationService):
    """Meta WhatsApp Cloud API sender (Stage 6). Requires
    WHATSAPP_PHONE_NUMBER_ID / WHATSAPP_ACCESS_TOKEN / WHATSAPP_RECIPIENT_NUMBERS."""

    API_BASE = "https://graph.facebook.com/v19.0"

    def __init__(self, cooldown_seconds: float = 120.0):
        super().__init__(cooldown_seconds)
        self.phone_number_id = settings.whatsapp_phone_number_id
        self.access_token = settings.whatsapp_access_token
        self.recipients = [r.strip() for r in settings.whatsapp_recipient_numbers.split(",") if r.strip()]

    def _send(self, alert: AlertMessage):
        if not (self.phone_number_id and self.access_token and self.recipients):
            logger.warning("WhatsApp notification requested but not fully configured — falling back to console")
            logger.warning(f"[SOUVENO VISION ALERT] {alert.title} — {alert.body}")
            return
        import requests
        text = f"SOUVENO VISION ALERT\n\n{alert.title}\n{alert.body}\nBranch: {alert.branch}"
        url = f"{self.API_BASE}/{self.phone_number_id}/messages"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        for recipient in self.recipients:
            payload = {"messaging_product": "whatsapp", "to": recipient, "type": "text", "text": {"body": text}}
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=10)
                if resp.status_code >= 300:
                    logger.error(f"WhatsApp send failed ({resp.status_code}): {resp.text[:200]}")
            except requests.RequestException as exc:
                logger.error(f"WhatsApp send error: {exc}")


def get_notification_service() -> NotificationService:
    if settings.notification_provider == "whatsapp":
        return WhatsAppNotificationService()
    return ConsoleNotificationService()

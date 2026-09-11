"""Credential redaction. Camera URLs, tokens and passwords must never reach a log
line, a screenshot, an API response or the database in clear text.

Use `mask_url()` for anything shown to a human, `redact_text()` for free text
(log messages, exception strings) and `build_rtsp_url()` to assemble a URL with
credentials that stays in memory only."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, unquote, urlsplit, urlunsplit

MASK = "***"

# scheme://user:pass@host  (any scheme) — captures the credential block.
_CRED_IN_URL = re.compile(r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.\-]*://)(?P<creds>[^/@\s]+)@")
_SENSITIVE_QUERY = re.compile(r"(?i)([?&](?:token|password|passwd|pwd|pass|key|apikey|api_key|auth|secret|signature|sig)=)([^&\s#]+)")
_SENSITIVE_KV = re.compile(r"(?i)\b(password|passwd|pwd|token|secret|api[_-]?key|authorization)(\s*[=:]\s*)(['\"]?)([^'\"\s,;]+)")
_SENSITIVE_KEY_NAMES = ("password", "passwd", "pwd", "token", "secret", "api_key", "apikey", "authorization", "auth")


def mask_url(url: str | None) -> str:
    """rtsp://admin:S3cret@10.0.0.5:554/ch1 -> rtsp://***:***@10.0.0.5:554/ch1"""
    if not url:
        return ""
    masked = _CRED_IN_URL.sub(lambda m: f"{m.group('scheme')}{MASK}:{MASK}@", url)
    masked = _SENSITIVE_QUERY.sub(lambda m: f"{m.group(1)}{MASK}", masked)
    return masked


def redact_text(text: Any) -> str:
    """Redact credentials embedded anywhere in free text (log lines, exception messages)."""
    if text is None:
        return ""
    s = str(text)
    s = _CRED_IN_URL.sub(lambda m: f"{m.group('scheme')}{MASK}:{MASK}@", s)
    s = _SENSITIVE_QUERY.sub(lambda m: f"{m.group(1)}{MASK}", s)
    s = _SENSITIVE_KV.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}{MASK}", s)
    return s


def redact_mapping(data: Any) -> Any:
    """Recursively redact dict/list structures before they are logged or exported."""
    if isinstance(data, dict):
        out = {}
        for k, v in data.items():
            if isinstance(k, str) and any(name in k.lower() for name in _SENSITIVE_KEY_NAMES):
                out[k] = MASK if v not in (None, "") else v
            else:
                out[k] = redact_mapping(v)
        return out
    if isinstance(data, (list, tuple)):
        return [redact_mapping(v) for v in data]
    if isinstance(data, str):
        return redact_text(data)
    return data


def url_has_credentials(url: str | None) -> bool:
    return bool(url) and _CRED_IN_URL.search(url) is not None


def strip_credentials(url: str) -> str:
    """Remove the user:pass@ part entirely (for storage: the DB keeps the host/path only)."""
    if not url:
        return ""
    return _CRED_IN_URL.sub(lambda m: m.group("scheme"), url)


def build_rtsp_url(url: str, username: str | None = None, password: str | None = None) -> str:
    """Return a URL with credentials injected (URL-encoded). If the URL already
    carries credentials and none are given, it is returned unchanged."""
    url = (url or "").strip()
    if not url:
        return ""
    if not username and not password:
        return url
    if url_has_credentials(url):
        url = strip_credentials(url)
    parts = urlsplit(url)
    userinfo = quote(username or "", safe="")
    if password:
        userinfo += ":" + quote(password, safe="")
    netloc = f"{userinfo}@{parts.hostname or ''}"
    if parts.port:
        netloc += f":{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def split_credentials(url: str) -> tuple[str, str | None, str | None]:
    """Return (url_without_credentials, username, password)."""
    if not url_has_credentials(url):
        return url, None, None
    parts = urlsplit(url)
    return strip_credentials(url), (unquote(parts.username) if parts.username else None), (unquote(parts.password) if parts.password else None)


def safe_filename(value: str, max_length: int = 80) -> str:
    """Whitelist-based filename sanitiser for evidence files."""
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value or "").strip("._")
    return (cleaned or "file")[:max_length]

"""Time helpers shared by every layer. All persisted timestamps are ISO-8601 UTC
with a trailing 'Z'; local time is only used for display and business hours."""
from __future__ import annotations

import time
from datetime import datetime, time as dtime, timedelta, timezone
from typing import Iterable, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso(dt: Optional[datetime] = None) -> str:
    dt = dt or now_utc()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(value: str) -> datetime:
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def resolve_tz(name: str | None):
    if not name or name == "local":
        return datetime.now().astimezone().tzinfo
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return datetime.now().astimezone().tzinfo


def to_local(dt: datetime, tz_name: str | None = "local") -> datetime:
    return dt.astimezone(resolve_tz(tz_name))


def local_display(dt: datetime, tz_name: str | None = "local") -> str:
    return to_local(dt, tz_name).strftime("%Y-%m-%d %H:%M:%S")


def parse_hhmm(value: str) -> dtime:
    hh, mm = value.strip().split(":")[:2]
    return dtime(int(hh), int(mm))


def is_within_business_hours(dt: datetime, start: str, end: str, days: Iterable[int],
                             tz_name: str | None = "local") -> bool:
    """True when the local time of `dt` falls inside [start, end) on an allowed weekday.
    Overnight windows (e.g. 22:00-06:00) are supported: the day is the day the window starts."""
    local = to_local(dt, tz_name)
    start_t, end_t = parse_hhmm(start), parse_hhmm(end)
    days = set(int(d) for d in days)
    t = local.time().replace(second=0, microsecond=0)
    if start_t <= end_t:
        return local.weekday() in days and start_t <= t < end_t
    # overnight window
    if t >= start_t:
        return local.weekday() in days
    if t < end_t:
        prev_day = (local - timedelta(days=1)).weekday()
        return prev_day in days
    return False


def monotonic() -> float:
    return time.monotonic()


def format_hms(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f} min"
    return f"{seconds / 3600:.1f} h"

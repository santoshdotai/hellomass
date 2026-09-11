"""Funds, grants, accelerators and Indian pavilions abroad — the 'Funds' tab.

Catalogue: data/expo/funds.json and data/expo/pavilions.json (researched 11 Sep 2026; the 3-day routine
re-checks deadlines and calls). Souveno AI Solutions (GSTIN 36BDNPP2011D2ZV) is a 1-year-old Hyderabad startup
with a 41-year-old founder: age of company and founder are checked against each scheme's window.
"""
from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from typing import Any

from config.settings import settings

FUNDS_PATH = settings.data_dir / "expo" / "funds.json"
PAVILIONS_PATH = settings.data_dir / "expo" / "pavilions.json"


@lru_cache(maxsize=1)
def _load() -> tuple[dict[str, Any], dict[str, Any]]:
    f = json.loads(FUNDS_PATH.read_text(encoding="utf-8"))
    p = json.loads(PAVILIONS_PATH.read_text(encoding="utf-8"))
    return f, p


def reload() -> None:
    _load.cache_clear()


def _priority(item: dict[str, Any], today: date) -> dict[str, Any]:
    fit = int(item.get("fit", 0))
    dl = item.get("deadline")
    days = (date.fromisoformat(dl) - today).days if dl else None
    urgency = "late" if (days is not None and days < 0) else "soon" if (days is not None and days <= 45) else "open" if item.get("rolling") else "dated"
    label = {5: "apply this month", 4: "apply this quarter", 3: "apply when needed", 2: "parked", 1: "not eligible / parked"}.get(fit, "parked")
    return {"days_to_deadline": days, "urgency": urgency, "priority_label": label, "priority_rank": (0 if urgency == "soon" else 1) * 10 + (5 - fit)}


def funds(region: str = "all", statuses: dict[str, dict[str, Any]] | None = None, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    f, _ = _load()
    rows = []
    for it in f["funds"]:
        if region != "all" and it["region"] != region:
            continue
        r = {**it, **_priority(it, today)}
        st = (statuses or {}).get(it["id"]) or {}
        r["status_app"] = st.get("status", "not_applied")
        r["applied_on"] = st.get("applied_on")
        r["notes_app"] = st.get("notes", "")
        rows.append(r)
    rows.sort(key=lambda r: (r["priority_rank"], r["name"]))
    return {"meta": f["_meta"], "region": region, "count": len(rows), "items": rows,
            "regions": [{"key": "india", "label": "India"}, {"key": "world", "label": "Rest of the world"}, {"key": "all", "label": "All"}],
            "summary": {"apply_this_month": [r["name"] for r in rows if r["fit"] >= 5], "cash_grants": [r["name"] for r in rows if r["type"] in ("grant", "matching funding", "incentives + accelerator", "grant + investment")]}}


def pavilions(today: date | None = None) -> dict[str, Any]:
    _, p = _load()
    rows = sorted(p["pavilions"], key=lambda r: (r["priority"], -r["fit"]))
    return {"meta": p["_meta"], "count": len(rows), "items": rows,
            "apply_first": [r["fair"] for r in rows if r["priority"] <= 2]}

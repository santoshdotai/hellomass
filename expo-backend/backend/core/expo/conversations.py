"""Organiser conversations: every mail sent, reply received and where the negotiation stands, per fair.

Source of truth is data/expo/conversations.json (written by the nightly desks and the backfill);
the API layers Santosh's edits and the desks' updates from the settings store on top.
Shape per event:
  {"eventId", "organiser", "email", "stage", "threadIds": [...], "lastAt", "lastDir",
   "messages": [{"at", "dir": "out|in|bounce", "from", "to", "subject", "snippet", "messageId", "threadId", "kind"}],
   "negotiation": {"sqm", "quoted_rate", "quoted_note", "regular_rate", "msme_rate", "our_counter_rate", "agreed_rate",
                   "ceiling_rate", "band", "includes_free": [], "optional_extras": [], "to_get": [], "next_step",
                   "verdict", "pending_action", "rounds": [{"at", "who", "rate", "note"}]}}
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.core.expo.catalog import get_event

DATA_FILE = Path(__file__).resolve().parents[3] / "data" / "expo" / "conversations.json"
NEG_FIELDS = ("sqm", "quoted_rate", "quoted_note", "regular_rate", "msme_rate", "our_counter_rate", "agreed_rate", "ceiling_rate", "band",
              "includes_free", "optional_extras", "to_get", "next_step", "verdict", "pending_action", "rounds")


def load_file() -> dict[str, dict[str, Any]]:
    if not DATA_FILE.exists():
        return {}
    raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return {c["eventId"]: c for c in raw.get("items", [])}


def save_file(items: dict[str, dict[str, Any]]) -> None:
    DATA_FILE.write_text(json.dumps({"items": sorted(items.values(), key=lambda c: c.get("lastAt") or "", reverse=True)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def merge(base: dict[str, Any] | None, patch: dict[str, Any]) -> dict[str, Any]:
    """Apply a patch: messages are appended (deduplicated by messageId), negotiation fields are merged, the rest replaced."""
    out = dict(base or {})
    for k, v in patch.items():
        if k == "messages":
            have = {m.get("messageId") for m in out.get("messages", []) if m.get("messageId")}
            out["messages"] = list(out.get("messages", [])) + [m for m in v if not m.get("messageId") or m["messageId"] not in have]
        elif k == "negotiation":
            neg = dict(out.get("negotiation") or {})
            for nk, nv in (v or {}).items():
                if nk == "rounds":
                    neg["rounds"] = list(neg.get("rounds", [])) + list(nv or [])
                else:
                    neg[nk] = nv
            out["negotiation"] = neg
        else:
            out[k] = v
    msgs = sorted(out.get("messages", []), key=lambda m: m.get("at") or "")
    out["messages"] = msgs
    if msgs:
        out["lastAt"], out["lastDir"] = msgs[-1].get("at"), msgs[-1].get("dir")
    out["count"] = len(msgs)
    return out


def all_conversations(overrides: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    items = load_file()
    for ev_id, patch in (overrides or {}).items():
        items[ev_id] = merge(items.get(ev_id), patch)
    rows = []
    for ev_id, c in items.items():
        ev = get_event(ev_id) or {}
        rows.append({**c, "eventId": ev_id, "eventName": ev.get("name", ev_id), "start": ev.get("start"), "city": ev.get("city"), "mode": ev.get("mode")})
    rows.sort(key=lambda c: c.get("lastAt") or "", reverse=True)
    return rows

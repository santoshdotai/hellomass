"""Layer 8 — repository/data-access layer. Raw SQL lives here and nowhere else."""
from __future__ import annotations

import csv
import io
import json
from typing import Any, Iterable, Optional

from src.security.redaction import redact_mapping
from src.storage.database import Database
from src.utils.time_utils import utc_iso


def _row(r) -> dict:
    return dict(r) if r is not None else None


class SourceRepository:
    def __init__(self, db: Database):
        self.db = db

    def upsert(self, source_id: str, name: str, kind: str, masked_url: str, spec: dict, stream_profile: str = "") -> dict:
        safe_spec = redact_mapping({k: v for k, v in spec.items() if k not in ("username", "password", "url")})
        now = utc_iso()
        self.db.execute(
            """INSERT INTO sources(source_id, name, kind, masked_url, spec_json, stream_profile, enabled, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
               ON CONFLICT(source_id) DO UPDATE SET name=excluded.name, kind=excluded.kind, masked_url=excluded.masked_url,
               spec_json=excluded.spec_json, stream_profile=excluded.stream_profile, updated_at=excluded.updated_at""",
            (source_id, name, kind, masked_url, json.dumps(safe_spec), stream_profile, now, now))
        return self.get(source_id)

    def get(self, source_id: str) -> Optional[dict]:
        r = self.db.query_one("SELECT * FROM sources WHERE source_id = ?", (source_id,))
        if r is None:
            return None
        d = _row(r)
        d["spec"] = json.loads(d.pop("spec_json") or "{}")
        return d

    def list(self) -> list[dict]:
        out = []
        for r in self.db.query("SELECT * FROM sources ORDER BY updated_at DESC"):
            d = _row(r)
            d["spec"] = json.loads(d.pop("spec_json") or "{}")
            out.append(d)
        return out

    def delete(self, source_id: str) -> None:
        self.db.execute("DELETE FROM sources WHERE source_id = ?", (source_id,))


class ZoneRepository:
    def __init__(self, db: Database):
        self.db = db

    def replace_for_source(self, source_id: str, zones: Iterable[dict]) -> list[dict]:
        now = utc_iso()
        with self.db.transaction() as db:
            db.conn.execute("DELETE FROM zones WHERE source_id = ?", (source_id,))
            for z in zones:
                db.conn.execute(
                    """INSERT INTO zones(zone_id, source_id, name, kind, points_json, color, enabled, dwell_threshold_seconds,
                       occupancy_limit, direction_flipped, in_label, out_label, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (z["zone_id"], source_id, z["name"], z["kind"], json.dumps(z["points"]), z.get("color", ""),
                     1 if z.get("enabled", True) else 0, z.get("dwell_threshold_seconds"), z.get("occupancy_limit"),
                     1 if z.get("direction_flipped") else 0, z.get("in_label", "Entry"), z.get("out_label", "Exit"), now, now))
        return self.list_for_source(source_id)

    def list_for_source(self, source_id: str) -> list[dict]:
        out = []
        for r in self.db.query("SELECT * FROM zones WHERE source_id = ? ORDER BY rowid", (source_id,)):
            d = _row(r)
            d["points"] = json.loads(d.pop("points_json"))
            d["enabled"] = bool(d["enabled"])
            d["direction_flipped"] = bool(d["direction_flipped"])
            out.append(d)
        return out

    def sources_with_zones(self) -> list[str]:
        return [r[0] for r in self.db.query("SELECT DISTINCT source_id FROM zones")]


class RuleRepository:
    def __init__(self, db: Database):
        self.db = db

    def upsert_many(self, rules: Iterable[dict]) -> None:
        now = utc_iso()
        rows = []
        for r in rules:
            rows.append((r["rule_id"], r["rule_type"], r.get("name", ""), 1 if r.get("enabled", True) else 0, r.get("source_id"),
                         r.get("zone_id"), r.get("threshold"), json.dumps(r.get("schedule") or {}), r.get("severity", "medium"),
                         float(r.get("cooldown_seconds", 30)), 1 if r.get("evidence_required", True) else 0,
                         1 if r.get("notify") else 0, now))
        self.db.executemany(
            """INSERT INTO rules(rule_id, rule_type, name, enabled, source_id, zone_id, threshold, schedule_json, severity,
               cooldown_seconds, evidence_required, notify, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(rule_id) DO UPDATE SET rule_type=excluded.rule_type, name=excluded.name, enabled=excluded.enabled,
               source_id=excluded.source_id, zone_id=excluded.zone_id, threshold=excluded.threshold,
               schedule_json=excluded.schedule_json, severity=excluded.severity, cooldown_seconds=excluded.cooldown_seconds,
               evidence_required=excluded.evidence_required, notify=excluded.notify, updated_at=excluded.updated_at""", rows)

    def list(self) -> list[dict]:
        out = []
        for r in self.db.query("SELECT * FROM rules ORDER BY rule_type"):
            d = _row(r)
            d["schedule"] = json.loads(d.pop("schedule_json") or "{}")
            d["enabled"] = bool(d["enabled"])
            d["evidence_required"] = bool(d["evidence_required"])
            d["notify"] = bool(d["notify"])
            out.append(d)
        return out

    def count(self) -> int:
        return int(self.db.query_one("SELECT COUNT(*) FROM rules")[0])


class EventRepository:
    COLUMNS = ("event_id", "event_type", "title", "rule_id", "source_id", "source_name", "zone_id", "zone_name", "track_id",
               "timestamp", "media_time", "severity", "confidence", "snapshot_path", "clip_path", "status", "acknowledged_by",
               "acknowledged_at", "notes", "metadata_json", "created_at")

    def __init__(self, db: Database):
        self.db = db

    def insert(self, event: dict) -> dict:
        e = dict(event)
        e.setdefault("created_at", utc_iso())
        e["metadata_json"] = json.dumps(e.pop("metadata", {}) or {})
        self.db.execute(
            f"INSERT INTO events({', '.join(self.COLUMNS)}) VALUES ({', '.join('?' for _ in self.COLUMNS)})",
            tuple(e.get(c) for c in self.COLUMNS))
        return self.get(e["event_id"])

    def update_paths(self, event_id: str, snapshot_path: str | None = None, clip_path: str | None = None) -> None:
        if snapshot_path is not None:
            self.db.execute("UPDATE events SET snapshot_path = ? WHERE event_id = ?", (snapshot_path, event_id))
        if clip_path is not None:
            self.db.execute("UPDATE events SET clip_path = ? WHERE event_id = ?", (clip_path, event_id))

    def set_status(self, event_id: str, status: str, actor: str | None = None, note: str | None = None) -> Optional[dict]:
        now = utc_iso()
        if status == "acknowledged":
            self.db.execute("UPDATE events SET status = ?, acknowledged_by = ?, acknowledged_at = ?, notes = CASE WHEN ? != '' THEN ? ELSE notes END WHERE event_id = ?",
                            (status, actor or "operator", now, note or "", note or "", event_id))
        else:
            self.db.execute("UPDATE events SET status = ?, notes = CASE WHEN ? != '' THEN ? ELSE notes END WHERE event_id = ?",
                            (status, note or "", note or "", event_id))
        return self.get(event_id)

    def get(self, event_id: str) -> Optional[dict]:
        r = self.db.query_one("SELECT * FROM events WHERE event_id = ?", (event_id,))
        return self._to_dict(r) if r else None

    @staticmethod
    def _to_dict(r) -> dict:
        d = _row(r)
        d["metadata"] = json.loads(d.pop("metadata_json") or "{}")
        return d

    def _where(self, f: dict) -> tuple[str, list]:
        clauses, params = [], []
        if f.get("date_from"):
            clauses.append("timestamp >= ?"); params.append(f["date_from"])
        if f.get("date_to"):
            clauses.append("timestamp <= ?"); params.append(f["date_to"])
        for key in ("source_id", "event_type", "severity", "status", "zone_id"):
            if f.get(key):
                clauses.append(f"{key} = ?"); params.append(f[key])
        if f.get("search"):
            clauses.append("(title LIKE ? OR notes LIKE ?)"); params += [f"%{f['search']}%", f"%{f['search']}%"]
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params

    def list(self, filters: dict | None = None, limit: int = 200, offset: int = 0) -> list[dict]:
        where, params = self._where(filters or {})
        rows = self.db.query(f"SELECT * FROM events{where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                             params + [int(limit), int(offset)])
        return [self._to_dict(r) for r in rows]

    def count(self, filters: dict | None = None) -> int:
        where, params = self._where(filters or {})
        return int(self.db.query_one(f"SELECT COUNT(*) FROM events{where}", params)[0])

    def count_by(self, column: str, filters: dict | None = None) -> dict[str, int]:
        if column not in ("event_type", "severity", "status", "source_id"):
            raise ValueError("unsupported column")
        where, params = self._where(filters or {})
        return {r[0]: int(r[1]) for r in self.db.query(f"SELECT {column}, COUNT(*) FROM events{where} GROUP BY {column}", params)}

    def distinct(self, column: str) -> list[str]:
        if column not in ("event_type", "severity", "status", "source_id", "source_name", "zone_name"):
            raise ValueError("unsupported column")
        return [r[0] for r in self.db.query(f"SELECT DISTINCT {column} FROM events WHERE {column} IS NOT NULL ORDER BY {column}")]

    def export_csv(self, filters: dict | None = None, limit: int = 10000) -> str:
        rows = self.list(filters, limit=limit)
        buf = io.StringIO()
        fields = ["event_id", "timestamp", "event_type", "title", "severity", "status", "source_id", "source_name", "zone_name",
                  "track_id", "confidence", "acknowledged_by", "acknowledged_at", "notes", "snapshot_path", "clip_path", "metadata"]
        writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for e in rows:
            e = dict(e)
            e["metadata"] = json.dumps(e.get("metadata", {}))
            writer.writerow(e)
        return buf.getvalue()

    def delete_older_than(self, iso_timestamp: str) -> int:
        cur = self.db.execute("DELETE FROM events WHERE timestamp < ?", (iso_timestamp,))
        return cur.rowcount

    def paths_older_than(self, iso_timestamp: str) -> list[tuple[str, str | None, str | None]]:
        return [(r[0], r[1], r[2]) for r in self.db.query(
            "SELECT event_id, snapshot_path, clip_path FROM events WHERE timestamp < ?", (iso_timestamp,))]


class AcknowledgementRepository:
    def __init__(self, db: Database):
        self.db = db

    def add(self, event_id: str, action: str, actor: str, note: str = "") -> dict:
        cur = self.db.execute("INSERT INTO acknowledgements(event_id, action, actor, note, created_at) VALUES (?, ?, ?, ?, ?)",
                              (event_id, action, actor, note or "", utc_iso()))
        return _row(self.db.query_one("SELECT * FROM acknowledgements WHERE ack_id = ?", (cur.lastrowid,)))

    def for_event(self, event_id: str) -> list[dict]:
        return [_row(r) for r in self.db.query("SELECT * FROM acknowledgements WHERE event_id = ? ORDER BY ack_id", (event_id,))]

    def recent(self, limit: int = 50) -> list[dict]:
        return [_row(r) for r in self.db.query("SELECT * FROM acknowledgements ORDER BY ack_id DESC LIMIT ?", (int(limit),))]


class SettingsRepository:
    def __init__(self, db: Database):
        self.db = db

    def get(self, key: str, default: Any = None) -> Any:
        r = self.db.query_one("SELECT value_json FROM application_settings WHERE key = ?", (key,))
        return json.loads(r[0]) if r else default

    def set(self, key: str, value: Any) -> None:
        self.db.execute("INSERT INTO application_settings(key, value_json, updated_at) VALUES (?, ?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at",
                        (key, json.dumps(value), utc_iso()))

    def all(self) -> dict:
        return {r[0]: json.loads(r[1]) for r in self.db.query("SELECT key, value_json FROM application_settings")}


class HealthLogRepository:
    def __init__(self, db: Database):
        self.db = db

    def add(self, snapshot: dict) -> None:
        self.db.execute(
            """INSERT INTO health_logs(recorded_at, source_id, source_status, capture_fps, inference_fps, latency_ms, dropped_frames,
               reconnects, cpu_percent, memory_percent, disk_free_mb, detector, device, details_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (utc_iso(), snapshot.get("source_id"), snapshot.get("source_status"), snapshot.get("capture_fps"),
             snapshot.get("inference_fps"), snapshot.get("latency_ms"), snapshot.get("dropped_frames"), snapshot.get("reconnects"),
             snapshot.get("cpu_percent"), snapshot.get("memory_percent"), snapshot.get("disk_free_mb"), snapshot.get("detector"),
             snapshot.get("device"), json.dumps(redact_mapping(snapshot.get("details", {})))))

    def recent(self, limit: int = 120) -> list[dict]:
        return [_row(r) for r in self.db.query("SELECT * FROM health_logs ORDER BY id DESC LIMIT ?", (int(limit),))]

    def prune(self, keep: int = 5000) -> None:
        self.db.execute("DELETE FROM health_logs WHERE id NOT IN (SELECT id FROM health_logs ORDER BY id DESC LIMIT ?)", (int(keep),))


class Repositories:
    """One object to pass around."""

    def __init__(self, db: Database):
        self.db = db
        self.sources = SourceRepository(db)
        self.zones = ZoneRepository(db)
        self.rules = RuleRepository(db)
        self.events = EventRepository(db)
        self.acks = AcknowledgementRepository(db)
        self.settings = SettingsRepository(db)
        self.health = HealthLogRepository(db)

"""Versioned SQLite migrations. Each entry runs once, in order; the applied
version is recorded in schema_version. Adding a column later = append a new
migration, never edit an old one."""
from __future__ import annotations

MIGRATIONS: list[tuple[int, str]] = [
    (1, """
    CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS sources (
        source_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        kind TEXT NOT NULL,
        masked_url TEXT DEFAULT '',
        spec_json TEXT DEFAULT '{}',          -- NEVER contains credentials
        stream_profile TEXT DEFAULT '',
        enabled INTEGER DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS zones (
        zone_id TEXT PRIMARY KEY,
        source_id TEXT NOT NULL,
        name TEXT NOT NULL,
        kind TEXT NOT NULL,
        points_json TEXT NOT NULL,            -- normalised [[x,y],...]
        color TEXT DEFAULT '',
        enabled INTEGER DEFAULT 1,
        dwell_threshold_seconds REAL,
        occupancy_limit INTEGER,
        direction_flipped INTEGER DEFAULT 0,
        in_label TEXT DEFAULT 'Entry',
        out_label TEXT DEFAULT 'Exit',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_zones_source ON zones(source_id);
    CREATE TABLE IF NOT EXISTS rules (
        rule_id TEXT PRIMARY KEY,
        rule_type TEXT NOT NULL,
        name TEXT NOT NULL,
        enabled INTEGER DEFAULT 1,
        source_id TEXT,
        zone_id TEXT,
        threshold REAL,
        schedule_json TEXT DEFAULT '{}',
        severity TEXT DEFAULT 'medium',
        cooldown_seconds REAL DEFAULT 30,
        evidence_required INTEGER DEFAULT 1,
        notify INTEGER DEFAULT 0,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS events (
        event_id TEXT PRIMARY KEY,
        event_type TEXT NOT NULL,
        title TEXT NOT NULL,
        rule_id TEXT,
        source_id TEXT NOT NULL,
        source_name TEXT NOT NULL,
        zone_id TEXT,
        zone_name TEXT,
        track_id INTEGER,
        timestamp TEXT NOT NULL,              -- ISO-8601 UTC
        media_time REAL,                      -- seconds into a recorded file, if any
        severity TEXT NOT NULL,
        confidence REAL,
        snapshot_path TEXT,
        clip_path TEXT,
        status TEXT NOT NULL DEFAULT 'new',   -- new | acknowledged | resolved | dismissed
        acknowledged_by TEXT,
        acknowledged_at TEXT,
        notes TEXT DEFAULT '',
        metadata_json TEXT DEFAULT '{}',
        created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp DESC);
    CREATE INDEX IF NOT EXISTS idx_events_source_ts ON events(source_id, timestamp DESC);
    CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
    CREATE INDEX IF NOT EXISTS idx_events_severity ON events(severity);
    CREATE INDEX IF NOT EXISTS idx_events_status ON events(status);
    CREATE TABLE IF NOT EXISTS acknowledgements (
        ack_id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL,
        action TEXT NOT NULL,                 -- acknowledged | resolved | dismissed | reopened
        actor TEXT NOT NULL,
        note TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        FOREIGN KEY(event_id) REFERENCES events(event_id)
    );
    CREATE INDEX IF NOT EXISTS idx_ack_event ON acknowledgements(event_id);
    CREATE TABLE IF NOT EXISTS application_settings (
        key TEXT PRIMARY KEY,
        value_json TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS health_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recorded_at TEXT NOT NULL,
        source_id TEXT,
        source_status TEXT,
        capture_fps REAL,
        inference_fps REAL,
        latency_ms REAL,
        dropped_frames INTEGER,
        reconnects INTEGER,
        cpu_percent REAL,
        memory_percent REAL,
        disk_free_mb REAL,
        detector TEXT,
        device TEXT,
        details_json TEXT DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_health_time ON health_logs(recorded_at DESC);
    """),
]

LATEST_VERSION = max(v for v, _ in MIGRATIONS)


def apply_migrations(conn) -> int:
    """Apply all pending migrations on an open sqlite3 connection. Returns the resulting version."""
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    current = int(row[0]) if row and row[0] is not None else 0
    from src.utils.time_utils import utc_iso
    for version, sql in MIGRATIONS:
        if version > current:
            conn.executescript(sql)
            conn.execute("INSERT OR REPLACE INTO schema_version(version, applied_at) VALUES (?, ?)", (version, utc_iso()))
            current = version
    conn.commit()
    return current

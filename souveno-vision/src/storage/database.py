"""Layer 8 — thread-safe SQLite connection wrapper with migrations and recovery.

* WAL journal mode so the dashboard can read while the pipeline writes;
* one connection guarded by an RLock (SQLite serialises writers anyway);
* every statement is parameterised — repositories never format SQL strings;
* a corrupt/unreadable database file is moved aside and recreated so the demo
  never fails to start because of a bad file."""
from __future__ import annotations

import shutil
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable, Optional

from loguru import logger

from src.storage.migrations import LATEST_VERSION, apply_migrations


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        self.version = 0
        self.recovered = False
        self.last_error = ""

    # ---- lifecycle ----------------------------------------------------------------
    def connect(self) -> "Database":
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._open()
        except sqlite3.DatabaseError as exc:
            logger.error(f"Database unreadable ({exc}); moving it aside and starting fresh")
            self._recover()
            self._open()
        return self

    def _open(self) -> None:
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False, timeout=10, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.DatabaseError:
            pass
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("SELECT count(*) FROM sqlite_master")  # raises on a corrupt file
        self.version = apply_migrations(self._conn)

    def _recover(self) -> None:
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
        self._conn = None
        if self.path.exists() and str(self.path) != ":memory:":
            backup = self.path.with_suffix(f".corrupt-{int(time.time())}.db")
            shutil.move(str(self.path), str(backup))
            for suffix in ("-wal", "-shm"):
                extra = Path(str(self.path) + suffix)
                if extra.exists():
                    extra.unlink()
        self.recovered = True

    def close(self) -> None:
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None

    # ---- statements ----------------------------------------------------------------
    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.connect()
        return self._conn  # type: ignore[return-value]

    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            try:
                return self.conn.execute(sql, tuple(params))
            except sqlite3.Error as exc:
                self.last_error = str(exc)
                raise

    def executemany(self, sql: str, rows: Iterable[Iterable[Any]]) -> None:
        with self._lock:
            self.conn.executemany(sql, [tuple(r) for r in rows])

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(sql, tuple(params)).fetchall()

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> Optional[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(sql, tuple(params)).fetchone()

    def transaction(self):
        return _Transaction(self)

    # ---- health ------------------------------------------------------------------
    def status(self) -> dict:
        ok = True
        detail = ""
        try:
            self.query_one("SELECT 1")
        except Exception as exc:
            ok, detail = False, str(exc)
        size_mb = round(self.path.stat().st_size / 1e6, 2) if self.path.exists() and str(self.path) != ":memory:" else 0.0
        return {"ok": ok, "path": str(self.path), "schema_version": self.version, "latest_version": LATEST_VERSION,
                "size_mb": size_mb, "recovered_from_corruption": self.recovered, "detail": detail or self.last_error}


class _Transaction:
    def __init__(self, db: Database):
        self.db = db

    def __enter__(self):
        self.db._lock.acquire()
        self.db.conn.execute("BEGIN")
        return self.db

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self.db.conn.execute("COMMIT")
            else:
                self.db.conn.execute("ROLLBACK")
        finally:
            self.db._lock.release()
        return False

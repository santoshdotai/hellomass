"""Lightweight, ordered schema migrations for the Solution Designer tables.

The project has no Alembic dependency, so migrations are Python callables
recorded in a `designer_schema_migrations` table. Each migration runs at
most once per database; `create_all` handles brand-new databases and
later migrations add columns/indexes on existing ones.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, inspect, text
from sqlalchemy.engine import Engine

from backend.db.database import Base

DESIGNER_TABLES = ("clients", "sites", "camera_groups", "cameras", "nvrs", "servers", "networks",
                   "use_cases", "assessments", "calculations", "recommendations", "proposals")


class DesignerSchemaMigration(Base):
    __tablename__ = "designer_schema_migrations"

    id = Column(Integer, primary_key=True)
    version = Column(String, unique=True, nullable=False)
    applied_at = Column(DateTime, default=datetime.utcnow)


def _m001_create_tables(engine: Engine) -> None:
    from backend.solution_designer import models  # noqa: F401  register tables on Base
    tables = [Base.metadata.tables[t] for t in DESIGNER_TABLES]
    Base.metadata.create_all(bind=engine, tables=tables)


def _m002_index_assessments_created(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_assessments_created_at ON assessments (created_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_cameras_site_id ON cameras (site_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_camera_groups_site_id ON camera_groups (site_id)"))


MIGRATIONS: list[tuple[str, callable]] = [
    ("001_create_designer_tables", _m001_create_tables),
    ("002_indexes", _m002_index_assessments_created),
]


def applied_versions(engine: Engine) -> list[str]:
    insp = inspect(engine)
    if "designer_schema_migrations" not in insp.get_table_names():
        return []
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT version FROM designer_schema_migrations ORDER BY id")).fetchall()
    return [r[0] for r in rows]


def run_migrations(engine: Engine) -> list[str]:
    """Apply pending migrations in order; returns the versions applied now."""
    Base.metadata.create_all(bind=engine, tables=[Base.metadata.tables["designer_schema_migrations"]])
    done = set(applied_versions(engine))
    applied_now = []
    for version, fn in MIGRATIONS:
        if version in done:
            continue
        fn(engine)
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO designer_schema_migrations (version, applied_at) VALUES (:v, :t)"),
                         {"v": version, "t": datetime.utcnow()})
        applied_now.append(version)
    return applied_now

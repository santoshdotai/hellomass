"""SQLAlchemy engine/session setup. SQLite for the demo (Phase 16);
swap DATABASE_URL to point at Postgres/Supabase for Stage 5 with no code changes here."""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from config.settings import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from backend.db import models  # noqa: F401  (register models on Base)
    Base.metadata.create_all(bind=engine)
    _add_missing_columns()


# columns added after the first release; create_all() only creates tables, so add them in place
_LATE_COLUMNS = {
    "expo_event_plans": [("flagged", "BOOLEAN DEFAULT 0"), ("flagged_at", "VARCHAR DEFAULT ''")],
}


def _add_missing_columns() -> None:
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, cols in _LATE_COLUMNS.items():
            if table not in insp.get_table_names():
                continue
            have = {c["name"] for c in insp.get_columns(table)}
            for name, ddl in cols:
                if name not in have:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))

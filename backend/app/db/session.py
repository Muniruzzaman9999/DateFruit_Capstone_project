"""Database connection and per-request sessions.

Vocabulary, in plain language:

* **engine**  - the pool of real network connections to PostgreSQL. Created
  once for the whole application, because opening a connection is expensive.
* **session** - a short-lived workspace for one unit of work. You add/read
  objects in it, then ``commit()`` to save. Each HTTP request gets its own.
"""

from __future__ import annotations

from collections.abc import Generator

# pyrefly: ignore [missing-import]
from sqlalchemy import create_engine
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# `pool_pre_ping=True` sends a cheap "are you still there?" check before
# reusing a pooled connection. Without it, a connection that died while the
# app was idle (laptop sleep, PostgreSQL restart) causes a confusing crash on
# the next request.
connect_args = {"check_same_thread": False, "timeout": 30} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    future=True,
    connect_args=connect_args,
)

if settings.database_url.startswith("sqlite"):
    from sqlalchemy import event  # noqa: E402

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

# `expire_on_commit=False` keeps loaded objects readable after commit().
# Without it, FastAPI would try to read an object's fields after the session
# committed, SQLAlchemy would go back to the database to refresh them, and
# because the request already finished you would get a DetachedInstanceError.
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that hands one database session to one request.

    Used as ``db: Session = Depends(get_db)`` in the route functions. The
    ``finally`` block guarantees the session is closed even if the request
    raises an error, so connections are never leaked.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

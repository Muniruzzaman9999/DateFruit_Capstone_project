"""SQLAlchemy declarative base and shared column mixins.

Every database table in this project is described by a Python class that
inherits from ``Base``. SQLAlchemy reads those classes and knows how to
create the real PostgreSQL tables, and how to turn table rows into Python
objects.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Parent class for all database models."""


class TimestampMixin:
    """Adds ``created_at`` / ``updated_at`` columns to a table.

    This is a plain mixin, not a table of its own. Both timestamps are filled
    in by PostgreSQL itself (``server_default=func.now()``) so the values are
    correct even if a row is inserted outside this application.

    ``timezone=True`` stores them as ``TIMESTAMPTZ`` (an instant in time,
    independent of the server's local timezone), which avoids a whole class of
    confusing bugs later.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

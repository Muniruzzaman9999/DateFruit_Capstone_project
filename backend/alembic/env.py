"""Alembic migration environment.

Two things in here were changed from the file Alembic generates by default:

1. **The database URL comes from ``backend/.env``**, not from ``alembic.ini``.
   That keeps your real password out of a file that gets committed to Git, and
   means there is only one place to configure the database.

2. **``target_metadata`` points at our models**, so ``alembic revision
   --autogenerate`` can compare the Python models against the real database
   and write the migration for us.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import create_engine, pool

from alembic import context

# ---------------------------------------------------------------------------
# Make the `app` package importable.
#
# Alembic runs this file directly, so `backend/` is not automatically on
# Python's import path. This file is at <project_root>/backend/alembic/env.py,
# so parents[1] is <project_root>/backend.
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# These imports must come *after* the sys.path change above, so the "imports
# should be at the top of the file" warning is suppressed on each line.
# `app.models` imports every model class, which is what makes autogenerate
# able to see all three tables.
from app.core.config import settings  # noqa: E402
from app.models import Base  # noqa: E402

# The Alembic Config object, i.e. the values from alembic.ini.
config = context.config

# Set up logging exactly as configured in alembic.ini.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# What the database *should* look like, according to our Python models.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Generate the SQL without connecting (``alembic upgrade head --sql``)."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect to PostgreSQL and apply the migrations.

    The URL is passed straight to ``create_engine`` instead of being written
    into the Alembic config. That matters because a password containing a
    ``%`` character would otherwise be mangled by the .ini file parser.

    ``NullPool`` means "do not keep connections around" - correct for a
    short-lived command-line tool.
    """
    connectable = create_engine(settings.database_url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Also notice when a column's *type* changed, not just when
            # columns were added or removed.
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

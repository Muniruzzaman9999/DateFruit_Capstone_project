"""Initialize database tables and seed date-fruit categories from model/classes.json."""

from __future__ import annotations

import json
import logging
from pathlib import Path

# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session

from app.core.config import CLASSES_PATH
from app.db.session import engine
from app.models import Base, CategorySource, DateFruitCategory, canonical_category_name

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_db() -> None:
    """Create tables if they don't exist and seed default categories."""
    logger.info("Creating database tables if needed...")
    Base.metadata.create_all(bind=engine)

    if not CLASSES_PATH.exists():
        logger.warning("CLASSES_PATH %s does not exist. Skipping seeding.", CLASSES_PATH)
        return

    try:
        raw_names = json.loads(CLASSES_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("Failed to read %s: %s", CLASSES_PATH, exc)
        return

    with Session(engine) as session:
        for raw in raw_names:
            name = canonical_category_name(str(raw))
            existing = (
                session.query(DateFruitCategory)
                .filter(DateFruitCategory.name == name)
                .first()
            )
            if not existing:
                category = DateFruitCategory(name=name, source=CategorySource.MODEL)
                session.add(category)
                logger.info("Seeded category: %s", name)
        session.commit()
    logger.info("Database initialization completed successfully.")


if __name__ == "__main__":
    init_db()

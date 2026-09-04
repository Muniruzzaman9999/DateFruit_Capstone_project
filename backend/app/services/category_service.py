"""Finding and creating date-fruit categories.

This is where the "no duplicate categories" rule is actually enforced, and it is
worth understanding that it takes *two* mechanisms working together:

1. :func:`app.models.category.canonical_category_name` decides what a name looks
   like once it is stored, so ``medjool``, ``MEDJOOL`` and `` Medjool `` all
   become the same string before anything is compared.
2. The UNIQUE index on ``date_fruit_categories.name`` makes a duplicate
   physically impossible, even if two requests slip past step 1 at the same
   instant.

Python alone would not be enough. Between "does Barhi exist?" and "insert Barhi"
there is a gap, and two people submitting Barhi together can both find nothing
and both insert. The database constraint closes that gap; the code below catches
the resulting error and hands back the row the other request created.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.category import (
    CategorySource,
    DateFruitCategory,
    canonical_category_name,
)

logger = logging.getLogger(__name__)


def list_categories(db: Session) -> list[DateFruitCategory]:
    """Every category, alphabetically.

    Alphabetical rather than grouped by source, because this list populates a
    dropdown and someone hunting for "Barhi" should find it where they expect.
    The ``source`` field travels with each row, so the interface can still mark
    which varieties the AI is able to recognise.
    """
    return list(db.scalars(select(DateFruitCategory).order_by(DateFruitCategory.name)))


def find_category_by_name(db: Session, raw_name: str) -> DateFruitCategory | None:
    """Look up a category by name, ignoring case and stray whitespace.

    Used when a prediction comes back from the model and the matching category
    row is needed. The model returns names exactly as they appear in
    ``classes.json``, and those were seeded in canonical form, so this always
    finds them - a test asserts that stays true.
    """
    name = canonical_category_name(raw_name)
    if not name:
        return None
    return db.scalars(
        select(DateFruitCategory).where(DateFruitCategory.name == name)
    ).first()


def get_or_create_category(
    db: Session, raw_name: str
) -> tuple[DateFruitCategory, bool]:
    """Return the category for this name, creating it if it is genuinely new.

    Returns ``(category, created)`` so the caller can answer 201 for a new
    category and 200 for one that already existed.

    A new category is always ``source=USER``. It exists in the database only: the
    trained model is untouched and cannot recognise it. Someone who adds "Barhi"
    can file listings under Barhi, but the AI will never predict Barhi - they
    will always have to choose it themselves. That is a deliberate limit of using
    a fixed pre-trained model, not an oversight.
    """
    name = canonical_category_name(raw_name)

    existing = db.scalars(
        select(DateFruitCategory).where(DateFruitCategory.name == name)
    ).first()
    if existing is not None:
        return existing, False

    category = DateFruitCategory(name=name, source=CategorySource.USER)
    db.add(category)
    try:
        db.commit()
    except IntegrityError:
        # Two requests created the same new category at the same moment and this
        # one lost the race. That is not an error worth showing anybody: the
        # category they asked for now exists, so fetch it and carry on.
        db.rollback()
        winner = db.scalars(
            select(DateFruitCategory).where(DateFruitCategory.name == name)
        ).first()
        if winner is None:
            # The failure was something other than a duplicate name, so it is a
            # real problem and must not be swallowed.
            raise
        logger.info("Category %r was created concurrently; reusing it.", name)
        return winner, False

    db.refresh(category)
    logger.info("Created new USER category %r (id=%s)", category.name, category.id)
    return category, True

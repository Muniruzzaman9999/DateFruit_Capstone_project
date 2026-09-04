"""The ``date_fruit_categories`` table: the date varieties a listing can use.

Where the categories come from
------------------------------
The application starts with the 9 varieties the trained model recognises, seeded
from ``model/classes.json`` (the single source of truth for those names). Users
may then add their own, for example "Barhi" or "Deglet Noor".

A user-added category exists **only in the database**. It does not become
something the model can recognise - the model is fixed and is never retrained.
So a listing in a user-added category is simply one where the person chose the
variety themselves instead of accepting the model's guess.

Preventing duplicates
---------------------
Without care the table would fill up with ``medjool``, ``Medjool``,
`` MEDJOOL `` and ``Medjool`` as four separate rows. Every name is therefore run
through :func:`canonical_category_name` before it is stored or looked up, and the
``name`` column carries a UNIQUE index. Normalising in Python decides *what* to
store; the UNIQUE index in PostgreSQL is what actually makes a duplicate
impossible, even if two people submit the same new name at the same instant.
"""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.listing import Listing


class CategorySource(str, enum.Enum):
    """Where a category came from.

    ``MODEL`` - one of the varieties the Keras model can actually predict.
    ``USER``  - added by a person through the application.

    Worth keeping separate: it lets the interface be honest about which
    varieties the AI can recognise and which it cannot.
    """

    MODEL = "MODEL"
    USER = "USER"


def canonical_category_name(raw: str) -> str:
    """Return the one spelling of a category name that gets stored.

    Three steps, and each one removes a way of accidentally creating a
    duplicate:

    1. ``.split()`` then ``" ".join(...)`` - drops leading and trailing spaces
       and collapses runs of inner whitespace, so ``" Nabtat   Ali "`` and
       ``"Nabtat Ali"`` end up identical.
    2. ``.title()`` - one consistent capitalisation, so ``medjool``,
       ``MEDJOOL`` and ``Medjool`` all become ``Medjool``.

    All 9 names in ``model/classes.json`` are already in this exact form, so
    seeding never alters a name the model depends on. A test asserts that,
    because if it ever stopped being true the stored category would no longer
    match what the model predicts.

    >>> canonical_category_name("  medjool ")
    'Medjool'
    >>> canonical_category_name("nabtat   ali")
    'Nabtat Ali'
    """
    return " ".join(raw.split()).title()


class DateFruitCategory(Base, TimestampMixin):
    """One date-fruit variety that listings can be filed under."""

    __tablename__ = "date_fruit_categories"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Stored in canonical form (see canonical_category_name above). UNIQUE is
    # the real duplicate guarantee, enforced by PostgreSQL rather than by us.
    name: Mapped[str] = mapped_column(
        String(80), nullable=False, unique=True, index=True
    )

    source: Mapped[CategorySource] = mapped_column(
        SAEnum(CategorySource, name="category_source"),
        nullable=False,
        default=CategorySource.USER,
        server_default=CategorySource.USER.value,
        index=True,
    )

    # A category has many listings. There is deliberately NO cascade delete
    # here: see the ON DELETE RESTRICT on listings.category_id, which stops a
    # category being removed while listings still point at it.
    listings: Mapped[list["Listing"]] = relationship(back_populates="category")

    def __repr__(self) -> str:
        return (
            f"<DateFruitCategory id={self.id} name={self.name!r} "
            f"source={self.source.value}>"
        )

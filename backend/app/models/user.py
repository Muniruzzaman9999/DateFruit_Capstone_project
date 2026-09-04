"""The ``users`` table.

There is exactly one kind of account in this application. Every registered user
can classify an image, publish a listing, browse everyone else's listings, and
edit their own. There is only one kind of account, and deliberately no
``role`` column: permission questions are answered by *ownership* ("is this your
listing?"), never by a role.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:  # imported only for type hints, which avoids a circular import
    from app.models.listing import Listing


class User(Base, TimestampMixin):
    """One registered person."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String(120), nullable=False)

    # `unique=True` makes PostgreSQL itself refuse a duplicate email. Checking
    # in Python alone is not enough: two people could register the same address
    # at the same instant and both pass that check before either one inserts.
    # The database constraint is the real guarantee.
    email: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )

    # The bcrypt hash - never the password itself. A bcrypt hash is 60
    # characters; 255 leaves room if the hashing scheme ever changes.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # The account holder's own phone number, collected at registration.
    # Note this is separate from the contact number stored on each listing: a
    # user may advertise a different shop line than their personal number, and
    # may use different numbers on different listings.
    contact_number: Mapped[str] = mapped_column(String(30), nullable=False)

    # One user has many listings. `cascade="all, delete-orphan"` means deleting
    # a user also deletes their listings, so no orphaned rows are left behind.
    # `passive_deletes=True` lets PostgreSQL's ON DELETE CASCADE do the work in
    # one statement instead of SQLAlchemy loading every row first.
    listings: Mapped[list["Listing"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:  # handy when poking around in a Python shell
        return f"<User id={self.id} email={self.email!r} name={self.name!r}>"

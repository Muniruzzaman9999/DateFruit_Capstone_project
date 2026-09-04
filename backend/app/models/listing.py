"""The ``listings`` table: one priced offer of one date variety by one user.

How a price is expressed
------------------------
A listing says "this much money buys this much fruit":

    price = 800,  quantity = 1,    unit = kg      ->  Tk800 for 1 kg
    price = 180,  quantity = 200,  unit = gram    ->  Tk180 for 200 grams
    price = 25,   quantity = 1,    unit = piece   ->  Tk25 for 1 piece

Keeping ``quantity`` separate from ``price`` matters for two reasons. It lets a
seller advertise the way they actually would ("Tk180 for a 200 g packet") instead
of working out a per-gram figure by hand, and it is what makes the price
statistics comparable across differently packaged offers.

Money is never stored as a float
--------------------------------
``price`` is ``Numeric(10, 2)`` - an exact decimal, not a floating-point number.
In floating point ``0.1 + 0.2`` is not exactly ``0.3``, and rounding drift in
prices is not acceptable. This maps to Python's ``Decimal``.
"""

from __future__ import annotations

import enum
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, Numeric, String, case
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.category import DateFruitCategory
    from app.models.user import User


class ListingStatus(str, enum.Enum):
    """Whether other people can currently see this listing.

    Deactivating is never a delete. An INACTIVE row stays in the database, keeps
    its image, stays visible to its author under "My Listings", and can be
    reactivated later.
    """

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class ListingUnit(str, enum.Enum):
    """The units a seller may price in.

    Only three, on purpose. ``gram`` and ``kg`` are weights and can be compared
    with each other; ``piece`` cannot, because nobody has told us what one piece
    weighs.
    """

    GRAM = "gram"
    KG = "kg"
    PIECE = "piece"


#: 1 kg = 1000 g. A Decimal, not the int 1000, so the division below stays exact.
GRAMS_PER_KG = Decimal("1000")

#: The units that can be normalised to a price per gram. ``piece`` is absent by
#: design - see :meth:`Listing.price_per_gram`.
GRAM_BASED_UNITS: frozenset[ListingUnit] = frozenset(
    {ListingUnit.GRAM, ListingUnit.KG}
)


class Listing(Base, TimestampMixin):
    """One user's priced offer of one date variety."""

    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Who published it. Set from the login token, never from the request body,
    # so a listing's owner cannot be forged. ON DELETE CASCADE means deleting a
    # user cleans up their listings instead of leaving orphaned rows.
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Which variety. ON DELETE RESTRICT makes PostgreSQL refuse to remove a
    # category while any listing still points at it - that would otherwise
    # leave listings with no variety at all.
    category_id: Mapped[int] = mapped_column(
        ForeignKey("date_fruit_categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # A path relative to backend/, e.g. "uploads/listings/2b91d4c8.jpg" - never
    # an absolute Windows path, so the row is still valid on another computer.
    #
    # Nullable on purpose. The API requires an image when publishing, but if a
    # file ever went missing from disk we need to be able to record that
    # honestly rather than keep pointing at something that is not there.
    image_path: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Exact decimal money. See the module docstring.
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    # How much fruit that price buys. 3 decimal places so half-kilos and odd
    # weights work; defaults to 1, which is what "Tk800 per kg" means.
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(10, 3), nullable=False, default=Decimal("1"), server_default="1"
    )

    unit: Mapped[ListingUnit] = mapped_column(
        # values_callable makes PostgreSQL store the enum *values* ('gram',
        # 'kg', 'piece'). Without it SQLAlchemy would store the member NAMES
        # ('GRAM', 'KG', 'PIECE'), which is not what the API sends or returns.
        SAEnum(
            ListingUnit,
            name="listing_unit",
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
    )

    # Shop details live on the listing, not on the user, so one person can
    # advertise several shops and use a different contact line for each.
    shop_name: Mapped[str] = mapped_column(String(120), nullable=False)
    contact_number: Mapped[str] = mapped_column(String(30), nullable=False)
    # Plain text for now. GPS, maps and radius search are a future feature.
    shop_location: Mapped[str] = mapped_column(String(255), nullable=False)

    status: Mapped[ListingStatus] = mapped_column(
        SAEnum(ListingStatus, name="listing_status"),
        nullable=False,
        default=ListingStatus.ACTIVE,
        server_default=ListingStatus.ACTIVE.value,
        index=True,
    )

    user: Mapped["User"] = relationship(back_populates="listings")
    category: Mapped["DateFruitCategory"] = relationship(back_populates="listings")

    __table_args__ = (
        # Enforced by PostgreSQL, so a nonsense value cannot be stored even if a
        # bug slips past the API's own validation.
        CheckConstraint("price > 0", name="ck_listing_price_positive"),
        CheckConstraint("quantity > 0", name="ck_listing_quantity_positive"),
        # The marketplace query is "active listings of this category, cheapest
        # first". This one index covers the filter and the sort together.
        Index(
            "ix_listings_category_status_price",
            "category_id",
            "status",
            "price",
        ),
    )

    # ------------------------------------------------------------------
    # Derived values
    # ------------------------------------------------------------------
    @hybrid_property
    def price_per_gram(self) -> Decimal | None:
        """This listing's price for one gram, or ``None`` if not comparable.

        This is the single place the conversion rule lives, so the marketplace,
        the per-category average and the tests can never disagree about it.

            Tk800 for 1 kg      ->  800 / (1 * 1000)  =  Tk0.80 / gram
            Tk180 for 200 gram  ->  180 / 200         =  Tk0.90 / gram
            Tk25  for 1 piece   ->  None

        ``piece`` returns ``None`` because a piece cannot be converted to grams
        without knowing what one piece weighs, and nobody has told us. Mixing
        Tk/piece into an average of Tk/gram would produce a number that means
        nothing, so those listings are left out of the statistics entirely -
        while still appearing in the marketplace.

        No rounding happens here. Rounding is done once, at the point of
        display, so intermediate averages do not accumulate error.
        """
        if self.unit is ListingUnit.GRAM:
            return self.price / self.quantity
        if self.unit is ListingUnit.KG:
            return self.price / (self.quantity * GRAMS_PER_KG)
        return None

    @price_per_gram.expression
    @classmethod
    def price_per_gram(cls):
        """The same rule again, this time as SQL PostgreSQL can sort by.

        A ``@hybrid_property`` is a SQLAlchemy feature that lets one name mean two
        things: on a loaded object it runs the Python above, and in a query it
        becomes the ``CASE`` expression below. That matters because ordering
        thousands of listings by comparable price has to happen in the database -
        loading every row into Python to sort them there would not scale, and
        could not be combined with ``LIMIT``.

        Writing the rule twice is a risk, and it is why the two live side by side
        here rather than in separate files: a test asserts that both produce the
        same number for the same listing, so they cannot quietly drift apart.

        ``piece`` becomes SQL ``NULL``, the direct equivalent of Python's
        ``None``. Queries that sort by this must say what to do with NULLs, since
        PostgreSQL puts them first on an ascending sort by default - which would
        park every uncomparable listing at the top of a "cheapest first" list.
        """
        return case(
            (cls.unit == ListingUnit.GRAM, cls.price / cls.quantity),
            (cls.unit == ListingUnit.KG, cls.price / (cls.quantity * GRAMS_PER_KG)),
            else_=None,
        )

    def __repr__(self) -> str:
        return (
            f"<Listing id={self.id} category_id={self.category_id} "
            f"price={self.price} quantity={self.quantity} "
            f"unit={self.unit.value} status={self.status.value}>"
        )

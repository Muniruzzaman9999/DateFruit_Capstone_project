"""Price statistics: what a variety costs on average, and which is cheapest.

Everything here is calculated from the current rows, every time it is asked for.
Nothing is stored. That is a deliberate choice and it is what makes the numbers
trustworthy: the moment somebody edits a price, deactivates a listing or moves it to
another variety, the next request already reflects it. A stored average would need
invalidating in five different places, and the day one of them was missed the
application would start quoting figures that were no longer true.

The rule, in one place
----------------------
For one category:

1. take its ACTIVE listings only
2. keep the ones priced by gram or kg
3. convert each to a price for one gram
4. take the plain arithmetic mean of those

Worked through, with the specification's own example:

    Tk800 / kg      ->  Tk0.80 per gram
    Tk900 / kg      ->  Tk0.90 per gram
    Tk150 / 150 g   ->  Tk1.00 per gram
                        ----------------
    average          =  Tk0.90 per gram

Note that it is the mean of the *per-gram prices*, not a total divided by a total
weight. Three listings count equally, however much fruit each one is selling.

Why ``piece`` is left out
-------------------------
A piece cannot be turned into grams without knowing what one piece weighs, and
nobody has told us. Averaging Tk25/piece together with Tk0.80/gram would produce a
number that means nothing at all, so those listings sit out the statistics entirely -
while still appearing in the marketplace, where their own price is perfectly
meaningful.

In SQL this falls out for free, which is the neatest part of the design.
``Listing.price_per_gram`` is NULL for a piece listing, and both ``AVG`` and
``COUNT`` ignore NULLs - so the exclusion is not a special case anybody has to
remember to write.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models.category import CategorySource, DateFruitCategory
from app.models.listing import Listing, ListingStatus

logger = logging.getLogger(__name__)

#: How many decimal places an average is reported to.
#:
#: Four, not two. Per-gram prices are small numbers - Tk0.80 for a gram of dates -
#: so rounding an average to 2 places would flatten genuinely different varieties
#: into the same figure and make the "cheapest average" a coin toss between them.
#: Four places keeps the comparison meaningful. Round it to 2 when displaying it.
AVERAGE_DECIMAL_PLACES = 4

_QUANTUM = Decimal(1).scaleb(-AVERAGE_DECIMAL_PLACES)


def _round_average(value: Decimal | None) -> Decimal | None:
    """Round one average to the reported precision, or pass ``None`` through.

    Rounding happens here, once, before anything else looks at the number. That
    matters for a subtle reason: the "best average price" is chosen by comparing
    these values, so if the comparison used full precision while the response showed
    a rounded figure, a reply could name one category as cheapest while displaying
    two identical numbers. Rounding first means the winner is always visibly the
    winner.
    """
    if value is None:
        return None
    return Decimal(value).quantize(_QUANTUM, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class CategoryPriceStats:
    """One category's current price statistics.

    ``comparable_listing_count`` is the number the average is actually built from -
    ACTIVE listings priced by gram or kg. ``active_listing_count`` is every ACTIVE
    listing including the ones priced by the piece.

    Keeping both is what lets the interface be honest. A variety with four active
    piece listings and nothing else has no average at all, and "no price data"
    beside "4 listings for sale" explains itself, where a bare "0" would look like
    a bug.
    """

    category_id: int
    category_name: str
    category_source: CategorySource
    average_price_per_gram: Decimal | None
    comparable_listing_count: int
    active_listing_count: int

    @property
    def excluded_piece_count(self) -> int:
        """ACTIVE listings that could not join the average, all priced per piece."""
        return self.active_listing_count - self.comparable_listing_count

    @property
    def has_data(self) -> bool:
        return self.average_price_per_gram is not None


def collect_category_statistics(
    db: Session, *, category_id: int | None = None
) -> list[CategoryPriceStats]:
    """Current statistics for every category, or for one of them.

    Every category comes back, including those with nothing for sale - their average
    is ``None`` and their counts are zero. Deciding which of those to show is the
    caller's business, not this function's.

    One query does all of it. The alternative - loop over the categories, run a
    query each - would be the "N+1 query" problem: 20 varieties would mean 21 trips
    to the database to produce one small table.
    """
    # LEFT JOIN, with "is it active?" in the ON clause rather than in a WHERE.
    #
    # That distinction is the whole reason empty categories still appear. In a WHERE
    # clause, "status = ACTIVE" would be applied after the join and would throw away
    # the all-NULL row a LEFT JOIN produces for a category with no listings - which
    # silently turns the LEFT JOIN back into an ordinary INNER JOIN.
    active_listings_of_this_category = and_(
        Listing.category_id == DateFruitCategory.id,
        Listing.status == ListingStatus.ACTIVE,
    )

    statement = (
        select(
            DateFruitCategory.id,
            DateFruitCategory.name,
            DateFruitCategory.source,
            # AVG and COUNT both skip NULLs, and price_per_gram is NULL for a piece
            # listing - so piece listings are excluded from the average and from the
            # count it is based on, without a special case.
            func.avg(Listing.price_per_gram).label("average_price_per_gram"),
            func.count(Listing.price_per_gram).label("comparable_listing_count"),
            # COUNT of the id counts every ACTIVE listing, piece ones included.
            func.count(Listing.id).label("active_listing_count"),
        )
        .outerjoin(Listing, active_listings_of_this_category)
        .group_by(
            DateFruitCategory.id, DateFruitCategory.name, DateFruitCategory.source
        )
    )

    if category_id is not None:
        statement = statement.where(DateFruitCategory.id == category_id)

    return [
        CategoryPriceStats(
            category_id=row.id,
            category_name=row.name,
            category_source=row.source,
            average_price_per_gram=_round_average(row.average_price_per_gram),
            comparable_listing_count=row.comparable_listing_count,
            active_listing_count=row.active_listing_count,
        )
        for row in db.execute(statement).all()
    ]


def get_category_statistics(db: Session, category_id: int) -> CategoryPriceStats | None:
    """Statistics for one category, or ``None`` if no such category exists."""
    found = collect_category_statistics(db, category_id=category_id)
    return found[0] if found else None


def cheapest_average_first(
    stats: list[CategoryPriceStats],
) -> list[CategoryPriceStats]:
    """Only the categories that have an average, cheapest first.

    The name is the tie-breaker. Two varieties averaging exactly the same price would
    otherwise come back in whatever order the database found convenient, and the
    "best average" would appear to change at random between two identical requests.
    """
    with_data = [item for item in stats if item.has_data]
    return sorted(with_data, key=lambda item: (item.average_price_per_gram, item.category_name))


def best_average_category(
    stats: list[CategoryPriceStats],
) -> CategoryPriceStats | None:
    """The category with the lowest average price per gram, or ``None``.

    Worth being precise about what this claims, because the label invites the wrong
    reading. It means one thing only:

        the lowest arithmetic mean price per gram, among varieties that
        currently have at least one active listing priced by gram or kg

    It says nothing about quality, taste or popularity. A variety can top this list
    simply because it is the cheapest thing on the shelf.

    Categories with no comparable listings cannot win - not even by counting as
    zero. "No data" is not a low price.
    """
    ranked = cheapest_average_first(stats)
    return ranked[0] if ranked else None

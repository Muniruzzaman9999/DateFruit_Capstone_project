"""The shared marketplace: reading everybody's ACTIVE listings.

What makes it "shared"
----------------------
These queries deliberately do **not** filter by the person asking. Every logged-in
user sees every ACTIVE listing, their own included - that is the whole point of the
application. If User A lists Ajwa at Tk800/kg and User B lists it at Tk750/kg, both
of them see both offers and can compare.

The one filter that always applies is ``status = ACTIVE``. A deactivated listing is
invisible here to everybody, including its author, who sees it only under "My
Listings".

Why the sorting lives in SQL
----------------------------
Both orderings are done by PostgreSQL, not by Python. Fetching every listing in
order to sort it here would mean loading the whole table into memory, and it could
not be combined with ``LIMIT`` - you cannot ask for "the ten cheapest" if the
sorting happens after the rows arrive. The per-gram comparison is available in SQL
because :attr:`app.models.listing.Listing.price_per_gram` is a hybrid property,
which knows how to express itself both ways.
"""

from __future__ import annotations

import logging

# pyrefly: ignore [missing-import]
from sqlalchemy import func, select
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session

from app.models.listing import GRAM_BASED_UNITS, Listing, ListingStatus
from app.schemas.marketplace import MarketplaceSort
from app.services.listing_service import with_related

logger = logging.getLogger(__name__)


def _order_for(sort: MarketplaceSort):
    """The ORDER BY clause for one sort choice.

    Both orderings end with ``Listing.id``, which looks redundant but is not. Rows
    that tie on price would otherwise come back in whatever order PostgreSQL finds
    convenient, and that order is free to differ between two queries - so page 2
    could repeat a listing from page 1 or skip one entirely. A unique tie-breaker
    makes the ordering total, and therefore the paging reliable.
    """
    if sort is MarketplaceSort.PRICE_PER_GRAM:
        return (
            # NULLS LAST matters. price_per_gram is NULL for `piece` listings, and
            # PostgreSQL sorts NULLs *first* on an ascending sort by default -
            # which would put every uncomparable listing at the top of a
            # "cheapest first" list. They belong at the end.
            Listing.price_per_gram.asc().nulls_last(),
            Listing.price.asc(),
            Listing.id.asc(),
        )
    elif sort is MarketplaceSort.PRICE_DESC:
        return (Listing.price.desc(), Listing.id.desc())
    elif sort is MarketplaceSort.NEWEST:
        return (Listing.id.desc(),)
    return (Listing.price.asc(), Listing.id.asc())


def list_marketplace_listings(
    db: Session,
    *,
    category_id: int | None = None,
    sort: MarketplaceSort = MarketplaceSort.PRICE,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Listing], int]:
    """ACTIVE listings from every user, cheapest first.

    Returns ``(listings_for_this_page, total_matching)``. The total is counted
    separately from the page, so the caller can say "showing 20 of 57" rather than
    quietly presenting a truncated list as if it were everything.

    ``category_id`` narrows it to one variety. Left out, the whole marketplace
    comes back.
    """
    conditions = [Listing.status == ListingStatus.ACTIVE]
    if category_id is not None:
        conditions.append(Listing.category_id == category_id)

    total = (
        db.scalar(select(func.count()).select_from(Listing).where(*conditions)) or 0
    )

    listings = db.scalars(
        with_related(select(Listing).where(*conditions))
        .order_by(*_order_for(sort))
        .limit(limit)
        .offset(offset)
    ).all()

    return list(listings), total


def find_best_priced_listing(db: Session, category_id: int) -> Listing | None:
    """The single cheapest *comparable* ACTIVE listing in one category.

    "Comparable" is the important word, and it is why this cannot simply be the
    lowest price on the card. Consider two real offers:

        Tk180 for a 200 g packet   ->  Tk0.90 per gram
        Tk800 for 1 kg             ->  Tk0.80 per gram

    Tk180 is the smaller number, but it is the *worse* deal. Announcing it as the
    best price would be actively misleading, so the comparison is made per gram.

    ``piece`` listings are excluded for the same reason they are excluded from the
    averages: without knowing what one piece weighs there is no honest way to
    compare Tk25/piece with Tk0.80/gram. Those listings still appear in the
    marketplace itself - they just cannot win a contest that is measured in grams.

    Returns ``None`` if the category has no comparable ACTIVE listings at all,
    which the caller must report as "no price data" rather than as a price of zero.
    """
    return db.scalars(
        with_related(
            select(Listing).where(
                Listing.status == ListingStatus.ACTIVE,
                Listing.category_id == category_id,
                Listing.unit.in_(GRAM_BASED_UNITS),
            )
        )
        # id as the tie-breaker so two identically priced offers always produce the
        # same winner, instead of the answer changing between page loads.
        .order_by(Listing.price_per_gram.asc(), Listing.id.asc())
        .limit(1)
    ).first()

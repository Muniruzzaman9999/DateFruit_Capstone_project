"""Shared marketplace endpoints.

    GET /api/marketplace/listings     everybody's ACTIVE listings, cheapest first
    GET /api/marketplace/best-price   the cheapest comparable offer in one category

Both require a login, and neither filters by who is asking. That is the point: this
is a shared marketplace, so User A sees User B's offers and vice versa. The only
listings hidden here are INACTIVE ones, which are invisible to everybody - their
author sees them under "My Listings" instead.

Reading is open to all; changing is not. Editing, deactivating and reactivating live
in ``app/routers/listings.py`` and are restricted to each listing's author.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.deps import CurrentUser, DbSession
from app.schemas.listing import ListingCategory, ListingResponse
from app.schemas.marketplace import (
    BestPriceResponse,
    MarketplaceListingsResponse,
    MarketplaceSort,
)
from app.services.listing_service import get_category_or_404
from app.services.marketplace_service import (
    find_best_priced_listing,
    list_marketplace_listings,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])

#: The largest page the API will hand out, and the size it gives by default.
#: A cap exists because every listing on a page carries a photo the browser then
#: downloads; an uncapped request on a busy marketplace would be a slow page for
#: no benefit. The response always reports the true `total`, so a capped page is
#: visible to the caller rather than silently passing for the whole marketplace.
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 200


@router.get(
    "/listings",
    response_model=MarketplaceListingsResponse,
    summary="Browse everybody's active listings",
)
def read_marketplace_listings(
    user: CurrentUser,
    db: DbSession,
    category_id: Annotated[
        int | None,
        Query(
            gt=0,
            description=(
                "Show only this variety, by id from GET /api/categories. Omit it "
                "for the whole marketplace."
            ),
        ),
    ] = None,
    sort: Annotated[
        MarketplaceSort,
        Query(
            description=(
                "`price` orders by the figure printed on the card, lowest first. "
                "`price_per_gram` orders by comparable value instead, which is the "
                "one to use when offers are packaged differently."
            )
        ),
    ] = MarketplaceSort.PRICE,
    limit: Annotated[
        int,
        Query(ge=1, le=MAX_PAGE_SIZE, description="How many listings to return."),
    ] = DEFAULT_PAGE_SIZE,
    offset: Annotated[
        int, Query(ge=0, description="How many listings to skip, for paging.")
    ] = 0,
) -> MarketplaceListingsResponse:
    """Every ACTIVE listing published by anyone, cheapest first.

    Your own listings appear here too, alongside everyone else's - the results are
    not filtered by who is asking. Deactivated listings never appear, whoever asks.

    Prices are shown exactly as their seller entered them, in their own unit. The
    ordering is a separate question from the display: see the `sort` parameter, and
    note that `price` can put a small-packet price above a better per-kilo one,
    because it is ordering the numbers on the cards rather than judging value.

    An unknown `category_id` is a 404 rather than an empty list, because "that
    variety does not exist" and "that variety has nothing for sale" are different
    answers and the interface should be able to tell them apart.
    """
    category = None
    if category_id is not None:
        category = get_category_or_404(db, category_id)

    listings, total = list_marketplace_listings(
        db, category_id=category_id, sort=sort, limit=limit, offset=offset
    )

    return MarketplaceListingsResponse(
        category=ListingCategory.model_validate(category) if category else None,
        sort=sort,
        total=total,
        count=len(listings),
        listings=[ListingResponse.from_listing(listing) for listing in listings],
    )


@router.get(
    "/best-price",
    response_model=BestPriceResponse,
    summary="The cheapest comparable offer for one variety",
)
def read_best_price(
    user: CurrentUser,
    db: DbSession,
    category_id: Annotated[
        int,
        Query(
            gt=0,
            description="Which variety to check, by id from GET /api/categories.",
        ),
    ],
) -> BestPriceResponse:
    """Where this variety is cheapest right now, per gram.

    Compared per gram rather than by the price on the card, because those two can
    disagree: Tk180 for a 200 g packet is a smaller number than Tk800 for a kilo,
    but it is the more expensive fruit. Ranking by the card price would hand the
    "best price" badge to the dearer offer.

    ``piece`` listings cannot join in - there is no way to convert a piece to grams
    without knowing what one weighs - so a category selling only by the piece has no
    best price, and says so. A category with nothing active for sale says so too,
    rather than reporting a price of zero.

    The complete winning listing comes back, photo and shop details included, so it
    can be displayed as a card without a second request.
    """
    category = get_category_or_404(db, category_id)
    listing = find_best_priced_listing(db, category_id)

    if listing is None:
        return BestPriceResponse(
            category=ListingCategory.model_validate(category),
            listing=None,
            message=(
                f"No comparable price data for {category.name} yet. Only active "
                "listings priced by gram or kg can be compared."
            ),
        )

    return BestPriceResponse(
        category=ListingCategory.model_validate(category),
        listing=ListingResponse.from_listing(listing),
        message=(
            f"Cheapest comparable offer for {category.name}: "
            f"{listing.shop_name} at {listing.price} per {listing.quantity} "
            f"{listing.unit.value}."
        ),
    )

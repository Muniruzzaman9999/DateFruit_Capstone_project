"""Response shapes for the shared marketplace.

Two ideas here are worth separating clearly, because the specification treats them
as different things and mixing them up produces misleading numbers.

**The card keeps the seller's own units.** A listing published as "Tk800 per kg" is
displayed as Tk800 per kg, always. It is never rewritten as Tk0.80 per gram just
because the comparison happens in grams.

**The comparison is per gram.** Deciding which offer is cheapest needs a common
measure, and grams are it. So ``price_per_gram`` travels alongside the original
price rather than replacing it - the interface shows one and ranks by the other.
"""

from __future__ import annotations

import enum

# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field

from app.schemas.listing import ListingCategory, ListingResponse


class MarketplaceSort(str, enum.Enum):
    """How to order the marketplace.

    ``price``
        The number printed on the card, lowest first. This is the default and what
        the specification asks for: Tk750, Tk800, Tk850.

        Be aware of what it does across mixed units, though. "Tk180 for 200 g"
        sorts above "Tk800 for 1 kg" because 180 is less than 800 - even though the
        packet is the dearer fruit per gram. It is an honest ordering of the prices
        on display, not a ranking of value.

    ``price_per_gram``
        The comparable price, lowest first, which is the one to use for "who is
        actually cheapest". ``piece`` listings have no per-gram price, so they sort
        to the end rather than being dropped.
    """

    PRICE = "price"
    PRICE_DESC = "price_desc"
    PRICE_PER_GRAM = "price_per_gram"
    NEWEST = "newest"


class MarketplaceListingsResponse(BaseModel):
    """A page of the marketplace."""

    category: ListingCategory | None = Field(
        default=None,
        description=(
            "The variety these results were filtered to, or null when the whole "
            "marketplace was requested. Echoed back so the interface can label the "
            "list without having to remember what it asked for."
        ),
    )
    sort: MarketplaceSort = Field(description="The ordering that was applied.")
    total: int = Field(
        description=(
            "How many ACTIVE listings match altogether - not just how many are in "
            "this response. Compare it with `count` to know whether there are more "
            "to fetch."
        ),
        examples=[57],
    )
    count: int = Field(
        description="How many listings are in this response.", examples=[20]
    )
    listings: list[ListingResponse]


class BestPriceResponse(BaseModel):
    """The cheapest comparable offer for one variety.

    This answers "where can I buy this most cheaply right now", using price per
    gram so that differently packaged offers can be judged against each other.
    """

    category: ListingCategory
    listing: ListingResponse | None = Field(
        default=None,
        description=(
            "The winning listing, with its photo, shop and contact details - or "
            "null when the category has no comparable ACTIVE listings. The whole "
            "listing is returned so the interface can show the offer exactly as it "
            "appears in the marketplace."
        ),
    )
    message: str = Field(
        description="A ready-to-display explanation, useful when there is no winner.",
        examples=["Cheapest comparable offer: Tk0.80 per gram."],
    )

"""Response shapes for the price statistics.

The exact wording of two fields is worth pinning down, because they are easy to
misread.

``average_price_per_gram`` is **null when there is no data**, never zero. Those mean
completely different things - "nobody is selling this by weight" against "it is
free" - and a zero would sort straight to the top of any cheapest-first list and
declare an empty category the best bargain in the marketplace.

``listing_count`` counts the listings the average is **actually built from**: ACTIVE
ones priced by gram or kg. A variety sold only by the piece therefore reports a count
of zero, which is why ``active_listing_count`` sits next to it - so the interface can
say "no comparable prices, though 4 listings are for sale" rather than a bare and
baffling zero.

A note on the numbers being text
--------------------------------
Prices and averages appear in JSON as strings (``"0.9000"``, not ``0.9``). That is
consistent with the rest of this API and it is deliberate: turning money into a
floating-point number is how rounding errors get in, since 0.1 + 0.2 is not exactly
0.3 in floating point. In JavaScript, wrap them in ``Number(...)`` before doing
arithmetic, and round to 2 decimal places for display.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.category import CategorySource
from app.services.statistics_service import CategoryPriceStats

#: The exact wording the interface shows when a variety has no comparable prices.
NO_DATA_MESSAGE = "No gram-based price data available"


class CategoryStatsResponse(BaseModel):
    """One category's current average price per gram."""

    category_id: int = Field(
        description="The category's id, for linking back to the marketplace.",
        examples=[3],
    )
    category: str = Field(description="The category's name.", examples=["Ajwa"])
    category_source: CategorySource = Field(
        description="MODEL if the AI can recognise this variety, USER if a person added it."
    )
    average_price_per_gram: Decimal | None = Field(
        description=(
            "The mean price of one gram across this category's active gram/kg "
            "listings, to 4 decimal places - or null if there are none. Never zero "
            "for 'no data'. Round to 2 places to display it."
        ),
        examples=["0.9000"],
    )
    listing_count: int = Field(
        description=(
            "How many active listings the average is built from: those priced by "
            "gram or kg. Piece listings are not counted here."
        ),
        examples=[3],
    )
    active_listing_count: int = Field(
        description="Every active listing in this category, piece ones included.",
        examples=[4],
    )
    excluded_piece_count: int = Field(
        description=(
            "Active listings left out of the average because they are priced per "
            "piece, which cannot be converted to grams."
        ),
        examples=[1],
    )
    message: str = Field(
        description=(
            "A ready-to-display sentence. When there is no data this is exactly "
            f"'{NO_DATA_MESSAGE}', so the interface can show it as-is."
        ),
        examples=["Average of 3 active listings priced by gram or kg."],
    )

    @classmethod
    def from_stats(cls, stats: CategoryPriceStats) -> "CategoryStatsResponse":
        if not stats.has_data:
            if stats.active_listing_count:
                message = (
                    f"{NO_DATA_MESSAGE} - all {stats.active_listing_count} active "
                    f"{stats.category_name} listing(s) are priced per piece, which "
                    "cannot be converted to grams."
                )
            else:
                message = f"{NO_DATA_MESSAGE} - no active {stats.category_name} listings."
        else:
            message = (
                f"Average of {stats.comparable_listing_count} active "
                f"{stats.category_name} listing(s) priced by gram or kg."
            )
            if stats.excluded_piece_count:
                message += (
                    f" {stats.excluded_piece_count} piece listing(s) were left out."
                )

        return cls(
            category_id=stats.category_id,
            category=stats.category_name,
            category_source=stats.category_source,
            average_price_per_gram=stats.average_price_per_gram,
            listing_count=stats.comparable_listing_count,
            active_listing_count=stats.active_listing_count,
            excluded_piece_count=stats.excluded_piece_count,
            message=message,
        )


class BestAveragePrice(BaseModel):
    """The variety with the lowest average price per gram.

    **This means the lowest calculated average price, and nothing else.** It is not a
    judgement about quality, taste or popularity - a variety can lead simply because
    it is the cheapest thing on the shelf. Please show that caveat next to it.
    """

    category_id: int = Field(examples=[7])
    category: str = Field(examples=["Rutab"])
    average_price_per_gram: Decimal = Field(examples=["0.7500"])
    listing_count: int = Field(
        description="How many active gram/kg listings that average is based on.",
        examples=[6],
    )

    @classmethod
    def from_stats(cls, stats: CategoryPriceStats) -> "BestAveragePrice":
        # has_data is guaranteed by best_average_category, which never returns a
        # category without an average - the assert documents that contract.
        assert stats.average_price_per_gram is not None
        return cls(
            category_id=stats.category_id,
            category=stats.category_name,
            average_price_per_gram=stats.average_price_per_gram,
            listing_count=stats.comparable_listing_count,
        )


class GlobalStatisticsResponse(BaseModel):
    """Average prices across every variety, and which one is cheapest."""

    categories: list[CategoryStatsResponse] = Field(
        description=(
            "Only the categories that currently have a comparable average, ordered "
            "cheapest average first - so the first entry is always the best average. "
            "A category with nothing for sale, or one sold only by the piece, is "
            "absent; ask GET /api/categories/{id}/stats about a specific one."
        )
    )
    best_average_price: BestAveragePrice | None = Field(
        default=None,
        description=(
            "The cheapest average, or null when no category has comparable data. "
            "Always the same as the first entry of `categories`."
        ),
    )
    counted_categories: int = Field(
        description="How many categories had comparable data.", examples=[4]
    )
    total_categories: int = Field(
        description=(
            "How many categories exist altogether, so the interface can say "
            "'4 of 11 varieties have price data'."
        ),
        examples=[11],
    )

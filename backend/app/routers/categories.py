"""Date-fruit category endpoints.

    GET  /api/categories                  every category, for the dropdowns
    POST /api/categories                  add one, or return the existing match
    GET  /api/categories/statistics       every category's average price, and the
                                          cheapest average of them all
    GET  /api/categories/{id}/stats       one category's average price

The statistics endpoints live here rather than under ``/api/marketplace`` because
they answer a question about a *category* - "what does Ajwa cost on average?" -
whereas the marketplace answers questions about individual listings.

Every figure they return is calculated from the current rows at the moment of the
request. Nothing is cached, so an edited price, a deactivated listing or a listing
moved to another variety is reflected immediately, with nothing to invalidate.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.core.deps import CurrentUser, DbSession
from app.schemas.category import (
    CategoryCreateRequest,
    CategoryListResponse,
    CategoryResponse,
)
from app.schemas.statistics import (
    BestAveragePrice,
    CategoryStatsResponse,
    GlobalStatisticsResponse,
)
from app.services.category_service import get_or_create_category, list_categories
from app.services.listing_service import get_category_or_404
from app.services.statistics_service import (
    best_average_category,
    cheapest_average_first,
    collect_category_statistics,
    get_category_statistics,
)

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get(
    "",
    response_model=CategoryListResponse,
    summary="List every date-fruit category",
)
def read_categories(user: CurrentUser, db: DbSession) -> CategoryListResponse:
    """The full category list: the 9 the model knows, plus any users have added.

    This is what fills the "select the correct variety" dropdown after a
    prediction, and the "choose a category" dropdown in the marketplace. It is
    read from the database every time, never from a hard-coded list, so a
    category added a moment ago appears immediately.
    """
    categories = list_categories(db)
    return CategoryListResponse(
        count=len(categories),
        categories=[CategoryResponse.model_validate(c) for c in categories],
    )


@router.post(
    "",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a date-fruit category",
)
def create_category(
    payload: CategoryCreateRequest,
    user: CurrentUser,
    db: DbSession,
    response: Response,
) -> CategoryResponse:
    """Add a new variety, or hand back the one that already matches.

    Submitting a name that already exists is **not** treated as an error. The
    specification's flow is "check whether it already exists, create it if it
    does not, then use it", and a person typing "Medjool" into the new-category
    box simply means they want Medjool - answering 409 would leave the interface
    with nothing usable and force it to make a second request.

    So the status code carries the distinction instead:

        201 Created  a genuinely new category was added
        200 OK       that category already existed; this is it

    Either way the response body is the category to file the listing under.
    """
    category, created = get_or_create_category(db, payload.name)
    if not created:
        response.status_code = status.HTTP_200_OK
    return CategoryResponse.model_validate(category)


# ---------------------------------------------------------------------------
# Price statistics
#
# "/statistics" is declared before "/{category_id}/stats" as a matter of habit.
# These two do not actually collide - one is a single path segment and the other
# is two - but FastAPI matches routes in the order they are declared, so a fixed
# word must always come before a variable that could swallow it. Written the other
# way round, a route like "/{category_id}" would read the word "statistics" as a
# category id and answer 422.
# ---------------------------------------------------------------------------
@router.get(
    "/statistics",
    response_model=GlobalStatisticsResponse,
    summary="Average price of every category, and the cheapest average",
)
def read_global_statistics(
    user: CurrentUser, db: DbSession
) -> GlobalStatisticsResponse:
    """Every variety's average price per gram, cheapest average first.

    This is what fills the price-comparison view: a table of averages, plus the one
    variety that is cheapest on average right now.

    Only varieties that **have** a comparable average appear. A variety with nothing
    for sale is left out rather than listed with a null, and a variety sold only by
    the piece is left out too - there is no honest way to average Tk/piece into
    Tk/gram. `total_categories` still reports how many exist altogether, so the
    interface can say "4 of 11 varieties have price data" instead of appearing to
    have lost some. Ask `GET /api/categories/{id}/stats` about a specific one.

    `best_average_price` is the cheapest of them, and is always the same as the first
    entry in `categories`. It is null only when no variety has any comparable data at
    all.

    **What "best" means here.** The lowest arithmetic mean price per gram. Nothing
    more. It is not a statement about quality, taste or popularity - a variety can
    lead this list purely by being the cheapest thing on the shelf, and the interface
    should say so alongside it.
    """
    all_stats = collect_category_statistics(db)
    ranked = cheapest_average_first(all_stats)
    best = best_average_category(all_stats)

    return GlobalStatisticsResponse(
        categories=[CategoryStatsResponse.from_stats(item) for item in ranked],
        best_average_price=BestAveragePrice.from_stats(best) if best else None,
        counted_categories=len(ranked),
        total_categories=len(all_stats),
    )


@router.get(
    "/{category_id}/stats",
    response_model=CategoryStatsResponse,
    summary="Average price of one category",
)
def read_category_statistics(
    category_id: int, user: CurrentUser, db: DbSession
) -> CategoryStatsResponse:
    """What one variety costs on average, per gram, right now.

    This is the "select a category and see its average" panel. The average covers
    that variety's ACTIVE listings priced by gram or kg; deactivated listings and
    piece listings do not count towards it.

    When there is nothing to average, `average_price_per_gram` is **null and never
    zero**, and `message` is a sentence beginning "No gram-based price data
    available" that can be displayed as-is. Those two states are genuinely
    different - "nobody is selling this by weight" is not the same as "it costs
    nothing" - and a zero would make an empty category look like the best bargain in
    the marketplace.

    `listing_count` is how many listings the average is built from. If a variety has
    four active listings all priced per piece, that count is 0 while
    `active_listing_count` is 4, so the interface can explain the difference rather
    than showing a bare zero that looks like a fault.
    """
    # 404 first, so an unknown id is answered clearly. Without this the statistics
    # query would simply return nothing, and "that variety does not exist" would be
    # indistinguishable from "that variety has no prices yet".
    get_category_or_404(db, category_id)

    stats = get_category_statistics(db, category_id)
    # get_category_or_404 has already established the row exists.
    assert stats is not None
    return CategoryStatsResponse.from_stats(stats)

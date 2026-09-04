"""Listing endpoints.

    POST  /api/listings                    publish one (multipart/form-data, with an image)
    GET   /api/listings/mine               my own listings, ACTIVE and INACTIVE
    GET   /api/listings/{id}               one listing
    PATCH /api/listings/{id}               edit my own listing
    POST  /api/listings/{id}/deactivate    hide my own listing
    POST  /api/listings/{id}/reactivate    show it again

The public marketplace - everyone's ACTIVE listings, with filtering and price
sorting - arrives in PHASE 9 as its own router.

Why publishing and editing are forms and not JSON
-------------------------------------------------
A JSON body cannot carry a file. Publishing sends the image and the listing
details together in one ``multipart/form-data`` request, so each field is declared
with ``Form(...)`` and the photo with ``File(...)``. In React this is a
``FormData`` object; the browser sets the content type itself.

Sending them together, rather than creating the listing and then uploading a
photo, means a listing never exists in a half-finished state with no image. Editing
uses the same form style for the same reason: replacing the photo and correcting
the price are one request, not two.

Who is allowed to do what
-------------------------
Reading an ACTIVE listing is open to every logged-in user - that is what makes the
marketplace shared. Changing one is restricted to its author, and that restriction
is enforced here on the server by
:func:`app.services.listing_service.get_owned_listing`, using the id from the
login token. Hiding the Edit button in React is a courtesy to the person using
the app, not a security measure.
"""

from __future__ import annotations

import logging
from typing import Annotated

# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Form, HTTPException, status

from app.core.deps import CurrentUser, DbSession
from app.core.uploads import read_image_upload
from app.models.listing import ListingStatus
from app.schemas.listing import (
    ListingCreateForm,
    ListingListResponse,
    ListingResponse,
    ListingUpdateForm,
)
from app.services.image_storage import UnreadableImageError, save_listing_image
from app.services.listing_service import (
    create_listing,
    get_category_or_404,
    get_owned_listing,
    get_viewable_listing,
    list_user_listings,
    set_listing_status,
    update_listing,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/listings", tags=["listings"])

#: How the publish and edit forms are sent.
#:
#: ``Form()`` on its own declares ``application/x-www-form-urlencoded``, which
#: cannot carry a file. FastAPI has no way to notice that the model contains an
#: ``UploadFile`` - it only sees "a model, sent as a form" - so the media type has
#: to be stated here.
#:
#: Without it the request still works, because the form parser follows the
#: request's own Content-Type header. What breaks is the documentation: /docs
#: would advertise the wrong media type and show the photo as a text box instead
#: of a file-picker button, so nobody could publish or edit a listing from the
#: Swagger page.
MULTIPART_FORM = Form(media_type="multipart/form-data")


def _save_uploaded_image_or_400(image_bytes: bytes) -> str:
    """Write validated image bytes to disk, turning a bad image into a 400.

    Shared by publishing and editing so both report an unreadable file the same
    way.
    """
    try:
        return save_listing_image(image_bytes)
    except UnreadableImageError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.post(
    "",
    response_model=ListingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Publish a listing",
)
async def publish_listing(
    user: CurrentUser,
    db: DbSession,
    form: Annotated[ListingCreateForm, MULTIPART_FORM],
) -> ListingResponse:
    """Publish a new listing, with its photo.

    The new listing is always ACTIVE, and its owner is taken from the login token
    - there is no ``user_id`` field to send, so a listing cannot be published in
    another person's name.

    ``Form()`` on a Pydantic model lets FastAPI validate every form field with the
    rules the schema declares and report problems as an ordinary 422, identical in
    shape to the errors a JSON endpoint returns. The image is a field of that same
    model, because FastAPI flattens a form model into separate fields only when it
    is the sole body parameter.

    The order of work matters, and it is: check the category exists, validate the
    image, save the image, then insert the row. Nothing is written to disk until
    everything that could be rejected has been checked, and if the insert fails
    anyway the file is removed again.
    """
    # --- 1. Does that category exist? -------------------------------------
    # Checked before touching the image, so a bad category id costs nothing.
    category = get_category_or_404(db, form.category_id)

    # --- 2. Validate the upload (type, then size) -------------------------
    image_bytes = await read_image_upload(form.image)


    # --- 3. Save the image ------------------------------------------------
    # This is the first thing that touches the disk. The stored name is random and
    # its extension comes from the file's real content, never from the name the
    # browser sent.
    image_path = _save_uploaded_image_or_400(image_bytes)

    # --- 4. Insert the row ------------------------------------------------
    listing = create_listing(
        db,
        user=user,
        category=category,
        image_path=image_path,
        price=form.price,
        quantity=form.quantity,
        unit=form.unit,
        shop_name=form.shop_name,
        contact_number=form.contact_number,
        shop_location=form.shop_location,
    )

    return ListingResponse.from_listing(listing)


@router.get(
    "/mine",
    response_model=ListingListResponse,
    summary="My listings (ACTIVE and INACTIVE)",
)
def read_my_listings(user: CurrentUser, db: DbSession) -> ListingListResponse:
    """Every listing you published, newest first.

    This is the "My Listings" section, and it is the only place a deactivated
    listing can be seen - the marketplace hides those from everyone, including
    their author. It is also where they are reactivated from (PHASE 8).

    The route is declared before ``/{listing_id}`` on purpose: FastAPI matches in
    the order routes are defined, so with them the other way round the word
    "mine" would be read as a listing id.
    """
    return ListingListResponse.from_listings(list_user_listings(db, user))


@router.get(
    "/{listing_id}",
    response_model=ListingResponse,
    summary="View one listing",
)
def read_listing(listing_id: int, user: CurrentUser, db: DbSession) -> ListingResponse:
    """One listing by id.

    An ACTIVE listing can be read by any logged-in user - that is what makes the
    marketplace shared. An INACTIVE one is visible only to its author; anybody
    else gets a 404, because a deactivated listing is meant to be hidden and a
    403 would confirm that it exists.
    """
    return ListingResponse.from_listing(get_viewable_listing(db, listing_id, user))


@router.patch(
    "/{listing_id}",
    response_model=ListingResponse,
    summary="Edit one of my listings",
)
async def edit_listing(
    listing_id: int,
    user: CurrentUser,
    db: DbSession,
    form: Annotated[ListingUpdateForm, MULTIPART_FORM],
) -> ListingResponse:
    """Change any part of a listing you published.

    Send only the fields that should change - correcting a price is one field, and
    everything else is left alone. Category, price, quantity, unit, shop name,
    contact number, shop location and the photo can all be edited.

    ``PATCH``, not ``PUT``, because this is a partial update: the request describes
    the difference, not a complete replacement listing.

    This updates the row that is already there. **The listing keeps its id**, so
    editing never produces a second copy of the same offer.

    To move a listing to a variety that does not exist yet, create it with
    ``POST /api/categories`` first - that endpoint normalises the name and hands
    back either the new category or the existing match - then send the id it
    returns as ``category_id``. Doing it that way means the "no duplicate
    categories" rule lives in exactly one place instead of being repeated here.

    Replies:

        200  the updated listing
        400  the request asked for no change at all, or the new photo is unreadable
        403  the listing belongs to somebody else
        404  no listing with that id, or no category with that id
        422  a field failed validation, for example a price of zero

    An edit to an ACTIVE listing takes effect immediately everywhere - marketplace
    order, best individual price and the per-gram averages are all worked out from
    the current rows whenever they are asked for, so there is no cached figure to
    go stale.
    """
    # --- 1. Is it mine? ---------------------------------------------------
    # First, before anything is validated or written: there is no point checking
    # a price on a listing this person is not allowed to touch. 404 if it does
    # not exist, 403 if it belongs to someone else.
    listing = get_owned_listing(db, listing_id, user)

    # --- 2. Was anything actually sent? -----------------------------------
    if form.is_empty():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Nothing to change. Send at least one of: category_id, price, "
                "quantity, unit, shop_name, contact_number, shop_location, image."
            ),
        )

    changes = form.changed_fields()

    # --- 3. If the category is changing, does the new one exist? ----------
    # Checked here so an unknown id gets a clear 404 that names the endpoint to
    # call, rather than a foreign-key error from PostgreSQL at commit time.
    if "category_id" in changes:
        get_category_or_404(db, changes["category_id"])

    # --- 4. If there is a new photo, validate it and save it --------------
    # Written to disk before the row is updated, and the OLD file is deliberately
    # left in place for now - see update_listing() for why that order matters.
    new_image_path: str | None = None
    if form.image is not None:
        image_bytes = await read_image_upload(form.image)
        new_image_path = _save_uploaded_image_or_400(image_bytes)

    # --- 5. Update the row ------------------------------------------------
    updated = update_listing(
        db, listing=listing, changes=changes, new_image_path=new_image_path
    )
    return ListingResponse.from_listing(updated)


@router.post(
    "/{listing_id}/deactivate",
    response_model=ListingResponse,
    summary="Hide one of my listings",
)
def deactivate_listing(
    listing_id: int, user: CurrentUser, db: DbSession
) -> ListingResponse:
    """Take one of your listings out of the marketplace, without deleting it.

    This is **not** a delete. The row stays in the database, the photo stays on
    disk, and the listing stays visible to you under "My Listings" - it is simply
    marked INACTIVE, which means:

    * it disappears from the marketplace for everyone
    * it drops out of the cheapest-price results
    * it stops counting towards any category's average price
    * you can switch it back on at any time with the reactivate endpoint

    Sold out for a week? Deactivate it, and reactivate it when the next delivery
    arrives, with all its details intact.

    Deactivating something that is already INACTIVE is not an error - it is
    already in the state you asked for, so the listing comes back unchanged.

    Replies:

        200  the listing, now INACTIVE
        403  the listing belongs to somebody else
        404  no listing with that id
    """
    listing = get_owned_listing(db, listing_id, user)
    updated = set_listing_status(db, listing=listing, new_status=ListingStatus.INACTIVE)
    return ListingResponse.from_listing(updated)


@router.post(
    "/{listing_id}/reactivate",
    response_model=ListingResponse,
    summary="Show one of my listings again",
)
def reactivate_listing(
    listing_id: int, user: CurrentUser, db: DbSession
) -> ListingResponse:
    """Put a deactivated listing back into the marketplace.

    The reverse of deactivating. The listing becomes ACTIVE again and immediately
    reappears for everyone, at whatever price it now carries - so if you edited
    the price while it was hidden, the new price is what goes live.

    Reactivating something that is already ACTIVE is not an error.

    Replies:

        200  the listing, now ACTIVE
        403  the listing belongs to somebody else
        404  no listing with that id
    """
    listing = get_owned_listing(db, listing_id, user)
    updated = set_listing_status(db, listing=listing, new_status=ListingStatus.ACTIVE)
    return ListingResponse.from_listing(updated)

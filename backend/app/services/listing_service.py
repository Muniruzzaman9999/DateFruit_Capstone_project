"""Creating and fetching listings, and the ownership rule.

The one thing to take away from this file
-----------------------------------------
``get_owned_listing`` is where "only the author may change their own listing" is
actually enforced, on the server, using the id from the login token. Hiding an
Edit button in React is a courtesy to the person using the app; it is not
security, because anyone can send an HTTP request without going near the
interface. Every endpoint that modifies a listing goes through that function.

The distinction it draws matters too:

    404  no listing with that id exists at all
    403  it exists, but it belongs to somebody else

Some applications answer 404 in both cases to avoid revealing that a listing
exists. Here the listings are already public - every logged-in user can see all of
them in the marketplace - so there is nothing to hide, and a clear "that is not
yours" is far easier to understand.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models.category import DateFruitCategory
from app.models.listing import Listing, ListingStatus, ListingUnit
from app.models.user import User
from app.services.image_storage import delete_listing_image

logger = logging.getLogger(__name__)


def with_related(statement):
    """Load each listing's category and author in the same query.

    Without this, rendering 20 listings would fire one extra query for the
    category and another for the author of every single row - the "N+1 query"
    problem. ``joinedload`` fetches all of it at once.
    """
    return statement.options(
        joinedload(Listing.category), joinedload(Listing.user)
    )


def get_listing_or_404(db: Session, listing_id: int) -> Listing:
    """Fetch one listing by id, or raise 404."""
    listing = db.scalars(
        with_related(select(Listing).where(Listing.id == listing_id))
    ).first()

    if listing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No listing with id {listing_id}.",
        )
    return listing


def get_viewable_listing(db: Session, listing_id: int, user: User) -> Listing:
    """Fetch a listing this user is allowed to see.

    An ACTIVE listing may be read by any logged-in user - that is the whole point
    of a shared marketplace. An INACTIVE one may be read only by its author.

    Someone else asking for an INACTIVE listing gets **404, not 403**. A
    deactivated listing is supposed to be hidden, and answering "403 Forbidden"
    would confirm it exists, which is exactly what hiding it is meant to prevent.
    """
    listing = get_listing_or_404(db, listing_id)

    if listing.status is ListingStatus.INACTIVE and listing.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No listing with id {listing_id}.",
        )

    return listing


def get_owned_listing(db: Session, listing_id: int, user: User) -> Listing:
    """Fetch a listing, but only if this user published it.

    Raises 404 if it does not exist, or 403 if it belongs to someone else. Every
    endpoint that edits, deactivates or reactivates a listing must go through
    here - that is what makes the ownership rule real rather than cosmetic.
    """
    listing = get_listing_or_404(db, listing_id)

    if listing.user_id != user.id:
        logger.info(
            "User %s tried to modify listing %s, which belongs to user %s.",
            user.id,
            listing_id,
            listing.user_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This listing belongs to another user, so you cannot change it.",
        )

    return listing


def get_category_or_404(db: Session, category_id: int) -> DateFruitCategory:
    """Fetch a category by id, or raise 404 with a helpful message."""
    category = db.get(DateFruitCategory, category_id)
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No date-fruit category with id {category_id}. Call "
                "GET /api/categories for the current list."
            ),
        )
    return category


def create_listing(
    db: Session,
    *,
    user: User,
    category: DateFruitCategory,
    image_path: str,
    price: Decimal,
    quantity: Decimal,
    unit: ListingUnit,
    shop_name: str,
    contact_number: str,
    shop_location: str,
) -> Listing:
    """Save a new ACTIVE listing owned by ``user``.

    ``user`` is the account from the login token, never a value from the request
    body, so the owner cannot be forged.

    If the database rejects the row, the image file that was just written is
    deleted before the error is raised. Otherwise a failed publish would leave an
    orphaned file on disk that nothing refers to and nothing will ever clean up.
    """
    listing = Listing(
        user_id=user.id,
        category_id=category.id,
        image_path=image_path,
        price=price,
        quantity=quantity,
        unit=unit,
        # Already trimmed and whitespace-collapsed by ListingCreateForm, which is
        # the one place that cleaning happens - so it cannot be done differently
        # here and in the edit endpoint later.
        shop_name=shop_name,
        contact_number=contact_number,
        shop_location=shop_location,
        status=ListingStatus.ACTIVE,
    )

    db.add(listing)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        delete_listing_image(image_path)
        logger.exception("Could not save listing; removed its image file.")
        raise

    db.refresh(listing)
    logger.info(
        "User %s published listing %s (category %s).",
        user.id,
        listing.id,
        category.name,
    )
    return listing


def list_user_listings(db: Session, user: User) -> list[Listing]:
    """Every listing this user published - ACTIVE and INACTIVE alike.

    This is "My Listings". The author sees their deactivated listings here, which
    is the only place they appear, and where they can be reactivated from.

    Newest first, because the thing you just published is the thing you most
    likely want to look at.
    """
    return list(
        db.scalars(
            with_related(
                select(Listing)
                .where(Listing.user_id == user.id)
                .order_by(Listing.created_at.desc(), Listing.id.desc())
            )
        )
    )


def _reload(db: Session, listing: Listing) -> Listing:
    """Re-read a listing from the database after it has been changed.

    This exists to prevent one specific wrong answer. Changing
    ``listing.category_id`` updates the *number*, but the already-loaded
    ``listing.category`` object still describes the old variety - so the response
    would show the new id alongside the old name. Expiring the row forces
    SQLAlchemy to fetch it again, relationships included, and the caller gets
    something that genuinely matches what is now stored.
    """
    db.expire(listing)
    return get_listing_or_404(db, listing.id)


def _image_used_by_another_listing(
    db: Session, listing_id: int, image_path: str
) -> bool:
    """Is any *other* listing still pointing at this image file?

    Deleting a replaced image must never remove a photo that another listing is
    displaying. Every saved file gets its own random name, so in normal use the
    answer is always no - but "delete a file from disk" is not something to do on
    an assumption, and this check costs one indexed query.
    """
    other = db.scalars(
        select(Listing.id)
        .where(Listing.image_path == image_path, Listing.id != listing_id)
        .limit(1)
    ).first()
    return other is not None


def update_listing(
    db: Session,
    *,
    listing: Listing,
    changes: dict[str, object],
    new_image_path: str | None = None,
) -> Listing:
    """Apply an edit to an existing listing row and return the updated listing.

    ``listing`` must already have passed :func:`get_owned_listing`, so by the time
    we are here the ownership question is settled.

    This **updates the existing row**. The listing keeps its id, its author and
    its publication date; nothing is duplicated. ``updated_at`` moves on its own,
    because the column is declared with ``onupdate=func.now()``.

    The order of the last three steps is the important part
    ------------------------------------------------------
    When the photo is being replaced, the new file has already been written to
    disk by the time this function is called, and the old one is still there.
    So:

    1. point the row at the new file and commit
    2. only if that commit succeeded, delete the old file
    3. if it failed, delete the **new** file and leave the old one alone

    Doing it the other way round - deleting the old file first - would leave the
    listing pointing at a photo that no longer exists whenever the commit failed.
    A listing with a stale-but-present photo is a much better failure than a
    listing with a broken image.

    Nothing about the price statistics needs to be told an edit happened. Averages
    are calculated from the current rows every time they are asked for, never
    stored, so a new price is reflected the instant this commit lands.
    """
    old_image_path = listing.image_path

    for field, value in changes.items():
        setattr(listing, field, value)

    if new_image_path is not None:
        listing.image_path = new_image_path

    try:
        db.commit()
    except Exception:
        db.rollback()
        if new_image_path is not None:
            # The row was not saved, so nothing refers to this file. Removing it
            # keeps a failed edit from leaving an orphan on disk.
            delete_listing_image(new_image_path)
            logger.exception(
                "Could not save the edit to listing %s; removed the new image "
                "file and kept the old one.",
                listing.id,
            )
        else:
            logger.exception("Could not save the edit to listing %s.", listing.id)
        raise

    # Safe now: the database points at the new file, so the old one is unused.
    if (
        new_image_path is not None
        and old_image_path
        and old_image_path != new_image_path
        and not _image_used_by_another_listing(db, listing.id, old_image_path)
    ):
        delete_listing_image(old_image_path)

    updated = _reload(db, listing)
    logger.info(
        "User %s edited listing %s (fields: %s%s).",
        updated.user_id,
        updated.id,
        ", ".join(sorted(changes)) or "none",
        ", image" if new_image_path is not None else "",
    )
    return updated


def set_listing_status(
    db: Session, *, listing: Listing, new_status: ListingStatus
) -> Listing:
    """Deactivate or reactivate a listing. Never deletes anything.

    ``listing`` must already have passed :func:`get_owned_listing`.

    Deactivating sets ``status = INACTIVE`` and stops there. The row stays, the
    image file stays on disk, and the author still sees it under "My Listings" -
    because the whole point of INACTIVE rather than deleted is that it can be
    switched back on. Reactivating is the same operation in reverse.

    Asking for the status a listing already has is not an error. The listing is
    already in the state you wanted, so the request has nothing left to do and
    the row is returned untouched - which also means ``updated_at`` is not
    disturbed by a click that changed nothing.
    """
    if listing.status is new_status:
        logger.info(
            "Listing %s is already %s; nothing to change.",
            listing.id,
            new_status.value,
        )
        return listing

    listing.status = new_status
    db.commit()

    updated = _reload(db, listing)
    logger.info(
        "User %s set listing %s to %s.",
        updated.user_id,
        updated.id,
        new_status.value,
    )
    return updated

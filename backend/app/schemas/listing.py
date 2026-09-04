"""Request and response shapes for listings.

Two things here are worth understanding before reading the code.

**Publishing uses a form, not JSON.** A listing arrives with an image file
attached, and a file cannot be put inside a JSON body. So ``POST /api/listings``
is ``multipart/form-data``, and :class:`ListingCreateForm` describes the whole
form - the text fields *and* the image. The image belongs in the model rather
than as a separate parameter because FastAPI flattens a form model into
individual fields only when it is the one and only body parameter; adding a
second one alongside it makes FastAPI expect a field literally named "form"
instead.

**The owner is not a field.** There is deliberately no ``user_id`` in
:class:`ListingCreateForm` or :class:`ListingUpdateForm`. It comes from the login
token instead, so nobody can publish or edit a listing in somebody else's name by
editing the request.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import UploadFile
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.models.category import CategorySource
from app.models.listing import Listing, ListingStatus, ListingUnit
from app.schemas.common import ContactNumber
from app.services.image_storage import listing_image_url

#: Upper bounds on money and quantity. The database column is Numeric(10, 2),
#: which holds up to 99,999,999.99 - these limits keep a typo like a price of
#: 10^12 from reaching it and causing a database error instead of a clear reply.
MAX_PRICE = Decimal("9999999.99")
MAX_QUANTITY = Decimal("9999999.999")


def _tidy_text(value: str) -> str:
    """Collapse whitespace, and reject a value that is only whitespace.

    ``min_length=1`` alone is not enough: three spaces are three characters, so
    ``"   "`` satisfies it and would be stored as a blank shop name once trimmed.
    Doing this in the schema rather than deeper in the code means the value that
    was validated is exactly the value that gets saved.
    """
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError("This cannot be blank.")
    return cleaned


# ---------------------------------------------------------------------------
# One definition per field, shared by publishing and editing
#
# Publishing requires these fields and editing does not, but the *rules* must be
# identical - a price that is invalid when published cannot become acceptable
# when edited in. Writing each rule once, here, is what guarantees that. Two
# copies of "price must be greater than zero" is exactly how one of them ends up
# saying something different.
# ---------------------------------------------------------------------------
CategoryIdField = Annotated[
    int,
    Field(
        gt=0,
        description=(
            "Which variety this is, by id from GET /api/categories. To use a "
            "brand-new variety, create it with POST /api/categories first and "
            "use the id that comes back."
        ),
        examples=[3],
    ),
]

PriceField = Annotated[
    Decimal,
    Field(
        gt=Decimal("0"),
        le=MAX_PRICE,
        max_digits=10,
        decimal_places=2,
        description="The total asking price for `quantity` of `unit`.",
        examples=["850.00"],
    ),
]

QuantityField = Annotated[
    Decimal,
    Field(
        gt=Decimal("0"),
        le=MAX_QUANTITY,
        max_digits=10,
        decimal_places=3,
        description=(
            "How much fruit the price buys. Leave it at 1 for 'Tk850 per kg'; "
            "set it to 200 with unit=gram for 'Tk180 for a 200 g packet'."
        ),
        examples=["1"],
    ),
]

UnitField = Annotated[
    ListingUnit,
    Field(
        description=(
            "gram, kg or piece. Note that `piece` listings are shown in the "
            "marketplace but left out of the price-per-gram statistics, because "
            "nobody has said what one piece weighs."
        ),
        examples=["kg"],
    ),
]

ShopNameField = Annotated[
    str,
    Field(
        min_length=1,
        max_length=120,
        description="The shop selling it.",
        examples=["Rahim Dates Shop"],
    ),
    AfterValidator(_tidy_text),
]

ShopLocationField = Annotated[
    str,
    Field(
        min_length=1,
        max_length=255,
        description="Plain text for now - no map or GPS lookup.",
        examples=["Mirpur, Dhaka"],
    ),
    AfterValidator(_tidy_text),
]

#: The listing columns an edit is allowed to change. ``status`` is deliberately
#: absent - deactivating and reactivating have their own endpoints, so a routine
#: price correction can never hide a listing by accident. ``image_path`` is
#: absent too, because the file has to be written to disk before that column can
#: be given a value.
EDITABLE_FIELDS: tuple[str, ...] = (
    "category_id",
    "price",
    "quantity",
    "unit",
    "shop_name",
    "contact_number",
    "shop_location",
)


class ListingCreateForm(BaseModel):
    """The multipart form sent when publishing a listing.

    The status is not here: a new listing is always ACTIVE. Neither is the owner,
    which comes from the login token.
    """

    image: UploadFile = Field(
        description="The listing photo: JPG, JPEG, PNG or WEBP, up to 5 MB."
    )
    category_id: CategoryIdField
    price: PriceField
    quantity: QuantityField = Decimal("1")
    unit: UnitField
    shop_name: ShopNameField
    contact_number: ContactNumber
    shop_location: ShopLocationField


class ListingUpdateForm(BaseModel):
    """The multipart form sent when editing a listing. Every field is optional.

    How a partial edit works
    -----------------------
    Send only what should change. Leaving ``unit`` out does not blank it - it
    means "leave the unit alone". So correcting just a price is one field, and
    the rest of the listing is untouched.

    That is why every field here is optional with a default of ``None``, and why
    ``None`` is read as "not sent" rather than "set this to nothing": none of
    these columns is allowed to be empty in the database, so "clear the shop
    name" is not a request that could ever be honoured anyway.

    Two fields you will not find here
    --------------------------------
    ``status`` - deactivating and reactivating are separate endpoints. Bundling
    them in here would mean a mistyped field in a price correction could quietly
    hide a listing from the marketplace.

    ``user_id`` - ownership comes from the login token. Sending one is ignored,
    so an edit cannot hand somebody else's listing to yourself.
    """

    image: UploadFile | None = Field(
        default=None,
        description=(
            "A replacement photo: JPG, JPEG, PNG or WEBP, up to 5 MB. Omit it "
            "to keep the current one. When a new photo is accepted the old file "
            "is deleted from disk."
        ),
    )
    category_id: CategoryIdField | None = None
    price: PriceField | None = None
    quantity: QuantityField | None = None
    unit: UnitField | None = None
    shop_name: ShopNameField | None = None
    contact_number: ContactNumber | None = None
    shop_location: ShopLocationField | None = None

    @field_validator("image", mode="before")
    @classmethod
    def _ignore_empty_image(cls, value: Any) -> Any:
        """Read an empty file field as "keep the current photo".

        A form that contains a file input with nothing chosen still sends the
        field - as an empty string, or as a file part with no filename. Both mean
        the person did not pick a new photo, so both become ``None`` here rather
        than a confusing "that is not a valid file" error.

        Anything else is passed through untouched, so a genuinely broken value
        still gets the honest 422 it deserves.
        """
        if isinstance(value, str):
            return None if not value.strip() else value
        if value is not None and not getattr(value, "filename", None):
            return None
        return value

    def changed_fields(self) -> dict[str, Any]:
        """The columns this request actually asked to change.

        Skips anything that was not sent, so the returned dictionary can be
        applied to the database row as-is. The image is not in here: it is a file
        on disk rather than a column, and it has to be saved before the row can
        point at it.
        """
        return {
            name: value
            for name in EDITABLE_FIELDS
            if (value := getattr(self, name)) is not None
        }

    def is_empty(self) -> bool:
        """True if the request asked for no change at all.

        Answering 400 for this is friendlier than silently doing nothing: it is
        almost always a frontend sending the wrong field name, and a silent
        success would leave that bug to be discovered much later.
        """
        return self.image is None and not self.changed_fields()


class ListingCategory(BaseModel):
    """The variety a listing is filed under, as shown on its card."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str = Field(examples=["Medjool"])
    source: CategorySource


class ListingOwner(BaseModel):
    """Who published a listing - the "Posted by" line on the card.

    Only the id and the display name. The owner's email and personal phone
    number are not part of a public listing: the shop's own contact number is on
    the listing itself, which is the number a buyer is meant to call.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str = Field(examples=["Rahim"])


class ListingResponse(BaseModel):
    """One listing, with everything a card needs to display it.

    A note on ``price``, ``quantity`` and ``price_per_gram``: these are exact
    decimals, and they appear in JSON as **strings** (``"850.00"``, not
    ``850.0``). That is deliberate - turning money into a floating-point number
    is how rounding errors get in. In JavaScript, wrap them in ``Number(...)``
    before doing arithmetic, or just display them as they are.
    """

    id: int
    image_url: str | None = Field(
        description=(
            "Root-relative address of the listing photo, to be joined onto the "
            "API base address. Null only if the file went missing."
        ),
        examples=["/uploads/listings/9f2c8b1d.jpg"],
    )
    category: ListingCategory
    price: Decimal = Field(examples=["850.00"])
    quantity: Decimal = Field(examples=["1.000"])
    unit: ListingUnit
    price_per_gram: Decimal | None = Field(
        description=(
            "The price of one gram, for comparing offers. Null for `piece` "
            "listings, which cannot be converted to a weight. Not rounded - "
            "round it when displaying it."
        ),
        examples=["0.85"],
    )
    shop_name: str
    contact_number: str
    shop_location: str
    status: ListingStatus
    posted_by: ListingOwner
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_listing(cls, listing: Listing) -> "ListingResponse":
        """Build the response for one database row.

        Written out by hand rather than left to ``from_attributes``, because two
        fields are not plain columns: ``image_url`` is derived from the stored
        path, and ``posted_by`` renames the ``user`` relationship to the label the
        specification asks for on the card.
        """
        return cls(
            id=listing.id,
            image_url=listing_image_url(listing.image_path),
            category=ListingCategory.model_validate(listing.category),
            price=listing.price,
            quantity=listing.quantity,
            unit=listing.unit,
            price_per_gram=listing.price_per_gram,
            shop_name=listing.shop_name,
            contact_number=listing.contact_number,
            shop_location=listing.shop_location,
            status=listing.status,
            posted_by=ListingOwner.model_validate(listing.user),
            created_at=listing.created_at,
            updated_at=listing.updated_at,
        )


class ListingListResponse(BaseModel):
    """A set of listings, for "My Listings" and for the marketplace."""

    count: int = Field(description="How many listings are in this response.")
    listings: list[ListingResponse]

    @classmethod
    def from_listings(cls, listings: list[Listing]) -> "ListingListResponse":
        items = [ListingResponse.from_listing(listing) for listing in listings]
        return cls(count=len(items), listings=items)

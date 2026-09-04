"""PHASE 13 - the specification's listing-creation and image test lists (section 74).

Covers: a user creates a listing, the image reference is saved, the published
image is written to disk, its URL is returned, and the file is reachable. Editing,
deactivating, reactivating and the ownership rules are in
``test_listings_edit.py``; the marketplace view is in ``test_marketplace.py``.

The two ideas being pinned down here
------------------------------------
**The owner comes from the login token, never from the request.** There is no
``user_id`` field to send, so a listing cannot be published in somebody else's
name. A test below sends one anyway to prove it is ignored.

**Nothing is written to disk until everything that could be rejected has been
checked.** The endpoint checks the category, then validates the upload, and only
then saves the file. A rejected request must not leave an orphaned photo behind,
because nothing would ever clean it up.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import LISTING_IMAGE_DIR, settings
from app.models.listing import Listing
from tests.conftest import (
    ApiUser,
    image_file_for,
    image_upload,
    make_image_bytes,
    publish_listing,
)


def form(category_id: int, **overrides) -> dict:
    """The listing form, with sensible defaults, overridable per test."""
    data = {
        "category_id": category_id,
        "price": "850.00",
        "quantity": "1",
        "unit": "kg",
        "shop_name": "Rahim Dates Shop",
        "contact_number": "01711222333",
        "shop_location": "Mirpur, Dhaka",
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------
def test_a_listing_publishes_with_every_field(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    response = alice.post(
        "/api/listings", data=form(category_ids["Medjool"]), files=image_upload()
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["category"]["name"] == "Medjool"
    assert Decimal(body["price"]) == Decimal("850.00")
    assert Decimal(body["quantity"]) == Decimal("1")
    assert body["unit"] == "kg"
    assert body["shop_name"] == "Rahim Dates Shop"
    assert body["contact_number"] == "01711222333"
    assert body["shop_location"] == "Mirpur, Dhaka"
    assert body["posted_by"]["id"] == alice.id
    assert body["posted_by"]["name"] == alice.name
    assert "created_at" in body and "updated_at" in body


def test_a_new_listing_is_always_active(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    listing = publish_listing(alice, category_ids["Ajwa"])
    assert listing["status"] == "ACTIVE"


def test_the_status_cannot_be_chosen_at_publish_time(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """``status`` is not a form field, so sending one must not hide the listing."""
    response = alice.post(
        "/api/listings",
        data=form(category_ids["Ajwa"], status="INACTIVE"),
        files=image_upload(),
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "ACTIVE"


def test_the_owner_comes_from_the_token_not_the_request(
    alice: ApiUser, bob: ApiUser, category_ids: dict[str, int]
) -> None:
    """Sending somebody else's user_id must not hand them the listing."""
    response = alice.post(
        "/api/listings",
        data=form(category_ids["Ajwa"], user_id=bob.id),
        files=image_upload(),
    )

    assert response.status_code == 201, response.text
    assert response.json()["posted_by"]["id"] == alice.id


def test_the_quantity_defaults_to_one(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """"Tk850 per kg" is quantity 1, so leaving it out must mean that."""
    data = form(category_ids["Ajwa"])
    del data["quantity"]

    response = alice.post("/api/listings", data=data, files=image_upload())

    assert response.status_code == 201, response.text
    assert Decimal(response.json()["quantity"]) == Decimal("1")


def test_all_three_units_are_accepted(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    for unit in ("gram", "kg", "piece"):
        response = alice.post(
            "/api/listings", data=form(category_ids["Ajwa"], unit=unit), files=image_upload()
        )
        assert response.status_code == 201, f"{unit}: {response.text}"
        assert response.json()["unit"] == unit


def test_a_kg_listing_gets_a_comparable_price_per_gram(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    listing = publish_listing(alice, category_ids["Ajwa"], price="800.00", unit="kg")
    # Tk800 for 1 kg = Tk0.80 per gram.
    assert Decimal(listing["price_per_gram"]) == Decimal("0.80")


def test_a_gram_listing_gets_a_comparable_price_per_gram(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    listing = publish_listing(
        alice, category_ids["Ajwa"], price="180.00", quantity="200", unit="gram"
    )
    # Tk180 for 200 g = Tk0.90 per gram.
    assert Decimal(listing["price_per_gram"]) == Decimal("0.90")


def test_a_piece_listing_has_no_comparable_price(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """Nobody has said what one piece weighs, so there is no honest per-gram figure."""
    listing = publish_listing(alice, category_ids["Ajwa"], price="25.00", unit="piece")
    assert listing["price_per_gram"] is None


def test_whitespace_in_the_text_fields_is_tidied(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    response = alice.post(
        "/api/listings",
        data=form(
            category_ids["Ajwa"],
            shop_name="  Rahim   Dates  Shop  ",
            shop_location="  Mirpur,   Dhaka ",
        ),
        files=image_upload(),
    )

    assert response.status_code == 201, response.text
    assert response.json()["shop_name"] == "Rahim Dates Shop"
    assert response.json()["shop_location"] == "Mirpur, Dhaka"


def test_the_new_listing_appears_in_my_listings(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    listing = publish_listing(alice, category_ids["Ajwa"])
    mine = alice.get("/api/listings/mine").json()
    assert listing["id"] in [row["id"] for row in mine["listings"]]


def test_the_new_listing_is_visible_to_another_user(
    alice: ApiUser, bob: ApiUser, category_ids: dict[str, int]
) -> None:
    """This is the shared marketplace: publishing makes it public immediately."""
    listing = publish_listing(alice, category_ids["Ajwa"])
    seen = bob.get("/api/marketplace/listings").json()
    assert listing["id"] in [row["id"] for row in seen["listings"]]


def test_publishing_requires_a_login(
    client: TestClient, category_ids: dict[str, int]
) -> None:
    response = client.post(
        "/api/listings", data=form(category_ids["Ajwa"]), files=image_upload()
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# The published image
# ---------------------------------------------------------------------------
def test_the_image_is_written_to_disk(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    listing = publish_listing(alice, category_ids["Ajwa"])
    assert image_file_for(listing).is_file()


def test_the_image_url_is_returned_and_root_relative(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    listing = publish_listing(alice, category_ids["Ajwa"])
    assert listing["image_url"].startswith("/uploads/listings/")


def test_the_image_is_reachable_over_http(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    listing = publish_listing(alice, category_ids["Ajwa"])

    response = alice.get(listing["image_url"])

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("image/")


def test_the_stored_path_is_relative_never_an_absolute_windows_path(
    alice: ApiUser, category_ids: dict[str, int], db: Session
) -> None:
    """An absolute path would break the moment the project moved machine.

    Portability is a hard requirement here, so the column has to hold something
    like ``uploads/listings/9f2c.jpg`` and nothing more.
    """
    listing = publish_listing(alice, category_ids["Ajwa"])
    row = db.scalars(select(Listing).where(Listing.id == listing["id"])).one()

    assert row.image_path.startswith("uploads/listings/")
    assert ":" not in row.image_path
    assert "\\" not in row.image_path
    assert not row.image_path.startswith("/")


def test_the_stored_filename_is_not_the_uploaded_one(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """The browser's filename is never trusted - it is where path tricks come from."""
    response = alice.post(
        "/api/listings",
        data=form(category_ids["Ajwa"]),
        files={"image": ("../../etc/passwd.jpg", make_image_bytes(), "image/jpeg")},
    )

    assert response.status_code == 201, response.text
    stored = response.json()["image_url"].rsplit("/", 1)[-1]
    assert "passwd" not in stored
    assert ".." not in stored
    assert "/" not in stored


def test_two_listings_get_two_different_files(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    first = publish_listing(alice, category_ids["Ajwa"], colour="red")
    second = publish_listing(alice, category_ids["Ajwa"], colour="blue")

    assert first["image_url"] != second["image_url"]
    assert image_file_for(first).is_file()
    assert image_file_for(second).is_file()


def test_the_extension_comes_from_the_content_not_the_filename(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """A real PNG named ".jpg" must be stored as a .png.

    Trusting the name would mean the file on disk lied about its own format.
    """
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (30, 30), "green").save(buffer, format="PNG")

    response = alice.post(
        "/api/listings",
        data=form(category_ids["Ajwa"]),
        files={"image": ("mislabelled.jpg", buffer.getvalue(), "image/png")},
    )

    assert response.status_code == 201, response.text
    assert response.json()["image_url"].endswith(".png")


def test_the_saved_bytes_are_the_bytes_that_were_uploaded(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """The photo on the card must be the photo that was sent, not a re-encode."""
    sent = make_image_bytes("purple")

    response = alice.post(
        "/api/listings",
        data=form(category_ids["Ajwa"]),
        files={"image": ("photo.jpg", sent, "image/jpeg")},
    )

    assert response.status_code == 201, response.text
    assert image_file_for(response.json()).read_bytes() == sent


# ---------------------------------------------------------------------------
# Refusing bad input
# ---------------------------------------------------------------------------
def test_a_price_of_zero_is_refused(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    response = alice.post(
        "/api/listings", data=form(category_ids["Ajwa"], price="0"), files=image_upload()
    )
    assert response.status_code == 422, response.text


def test_a_negative_price_is_refused(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    response = alice.post(
        "/api/listings", data=form(category_ids["Ajwa"], price="-5"), files=image_upload()
    )
    assert response.status_code == 422, response.text


def test_a_price_with_too_many_decimal_places_is_refused(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """The column is Numeric(10, 2), so three decimals cannot be stored honestly."""
    response = alice.post(
        "/api/listings",
        data=form(category_ids["Ajwa"], price="850.123"),
        files=image_upload(),
    )
    assert response.status_code == 422, response.text


def test_an_absurdly_large_price_is_refused(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """A typo must give a clear 422 rather than a database error."""
    response = alice.post(
        "/api/listings",
        data=form(category_ids["Ajwa"], price="99999999999"),
        files=image_upload(),
    )
    assert response.status_code == 422, response.text


def test_a_quantity_of_zero_is_refused(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """Zero would mean dividing by zero when working out the price per gram."""
    response = alice.post(
        "/api/listings", data=form(category_ids["Ajwa"], quantity="0"), files=image_upload()
    )
    assert response.status_code == 422, response.text


def test_an_unknown_unit_is_refused(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    response = alice.post(
        "/api/listings", data=form(category_ids["Ajwa"], unit="pound"), files=image_upload()
    )
    assert response.status_code == 422, response.text


def test_an_unknown_category_is_404(alice: ApiUser) -> None:
    response = alice.post("/api/listings", data=form(999999), files=image_upload())
    assert response.status_code == 404, response.text


def test_a_category_id_of_zero_is_refused(alice: ApiUser) -> None:
    response = alice.post("/api/listings", data=form(0), files=image_upload())
    assert response.status_code == 422, response.text


def test_a_blank_shop_name_is_refused(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """Three spaces satisfy ``min_length=1`` but are not a shop name."""
    response = alice.post(
        "/api/listings", data=form(category_ids["Ajwa"], shop_name="   "), files=image_upload()
    )
    assert response.status_code == 422, response.text


def test_a_blank_shop_location_is_refused(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    response = alice.post(
        "/api/listings",
        data=form(category_ids["Ajwa"], shop_location="  "),
        files=image_upload(),
    )
    assert response.status_code == 422, response.text


def test_an_implausible_contact_number_is_refused(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    response = alice.post(
        "/api/listings",
        data=form(category_ids["Ajwa"], contact_number="12"),
        files=image_upload(),
    )
    assert response.status_code == 422, response.text


def test_a_missing_image_is_refused(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """A listing must never exist without a photo."""
    response = alice.post("/api/listings", data=form(category_ids["Ajwa"]))
    assert response.status_code == 422, response.text


def test_an_unsupported_image_type_is_415(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    response = alice.post(
        "/api/listings",
        data=form(category_ids["Ajwa"]),
        files={"image": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 415, response.text


def test_an_empty_image_is_400(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    response = alice.post(
        "/api/listings",
        data=form(category_ids["Ajwa"]),
        files={"image": ("empty.jpg", b"", "image/jpeg")},
    )
    assert response.status_code == 400, response.text


def test_an_oversized_image_is_413(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    too_big = b"\xff\xd8\xff" + b"0" * (settings.max_upload_bytes + 1)
    response = alice.post(
        "/api/listings",
        data=form(category_ids["Ajwa"]),
        files={"image": ("huge.jpg", too_big, "image/jpeg")},
    )
    assert response.status_code == 413, response.text


def test_a_file_that_is_not_really_an_image_is_400(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    response = alice.post(
        "/api/listings",
        data=form(category_ids["Ajwa"]),
        files={"image": ("fake.jpg", b"definitely not a picture", "image/jpeg")},
    )
    assert response.status_code == 400, response.text


# ---------------------------------------------------------------------------
# A rejected request must leave nothing behind
# ---------------------------------------------------------------------------
def test_an_unknown_category_leaves_no_orphaned_photo(alice: ApiUser) -> None:
    """The category is checked before the image is saved, so nothing is written.

    An orphaned file would sit in ``backend/uploads/listings/`` forever, because
    no row points at it and nothing would ever clean it up.
    """
    before = set(LISTING_IMAGE_DIR.iterdir())

    assert alice.post("/api/listings", data=form(999999), files=image_upload()).status_code == 404

    assert set(LISTING_IMAGE_DIR.iterdir()) == before


def test_a_rejected_price_leaves_no_orphaned_photo(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    before = set(LISTING_IMAGE_DIR.iterdir())

    response = alice.post(
        "/api/listings", data=form(category_ids["Ajwa"], price="0"), files=image_upload()
    )
    assert response.status_code == 422

    assert set(LISTING_IMAGE_DIR.iterdir()) == before


def test_a_rejected_upload_leaves_no_orphaned_photo(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    before = set(LISTING_IMAGE_DIR.iterdir())

    response = alice.post(
        "/api/listings",
        data=form(category_ids["Ajwa"]),
        files={"image": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 415

    assert set(LISTING_IMAGE_DIR.iterdir()) == before

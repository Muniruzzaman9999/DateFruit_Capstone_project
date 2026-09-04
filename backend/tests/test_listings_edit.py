"""PHASE 8 - editing, deactivating and reactivating a listing.

What these tests are really checking
------------------------------------
Three promises the specification makes, each of which is easy to break:

**An edit updates the listing that is already there.** It keeps its id, its
author and its publication date. Nothing is duplicated - "edit the price" must
never quietly become "publish a second listing at the new price".

**Only the author may change a listing.** Enforced on the server from the login
token, so it holds even for a request that never went near the React app. A
hidden button is not a permission.

**Deactivating is not deleting.** The row stays, the photo stays on disk, and the
author can still see it and switch it back on.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import settings
from tests.conftest import (
    ApiUser,
    image_file_for,
    image_upload,
    make_image_bytes,
    publish_listing,
)


# ===========================================================================
# Editing - the fields
# ===========================================================================
def test_owner_can_edit_price(alice: ApiUser, category_ids: dict[str, int]) -> None:
    """Tk800/kg becomes Tk900/kg, on the same listing."""
    listing = publish_listing(alice, category_ids["Ajwa"], price="800.00", unit="kg")

    response = alice.patch(f"/api/listings/{listing['id']}", data={"price": "900.00"})

    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["id"] == listing["id"], "editing must not create a new listing"
    assert updated["price"] == "900.00"
    # The comparable figure is recalculated, not left at the old value.
    assert float(updated["price_per_gram"]) == 0.90


def test_owner_can_edit_category(alice: ApiUser, category_ids: dict[str, int]) -> None:
    """Ajwa becomes Medjool, and the response says so.

    This is the case that would expose a stale relationship: change only the
    ``category_id`` and it is entirely possible to reply with the new id beside
    the *old* name.
    """
    listing = publish_listing(alice, category_ids["Ajwa"])
    assert listing["category"]["name"] == "Ajwa"

    response = alice.patch(
        f"/api/listings/{listing['id']}",
        data={"category_id": category_ids["Medjool"]},
    )

    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["id"] == listing["id"]
    assert updated["category"]["id"] == category_ids["Medjool"]
    assert updated["category"]["name"] == "Medjool"


def test_owner_can_edit_unit_and_quantity(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """Tk800 per kg becomes Tk180 for a 200 g packet - Tk0.90 per gram."""
    listing = publish_listing(alice, category_ids["Ajwa"], price="800.00", unit="kg")

    response = alice.patch(
        f"/api/listings/{listing['id']}",
        data={"price": "180.00", "quantity": "200", "unit": "gram"},
    )

    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["unit"] == "gram"
    assert float(updated["quantity"]) == 200
    assert float(updated["price_per_gram"]) == 0.90


def test_switching_to_piece_removes_the_comparable_price(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """A ``piece`` listing has no price per gram, because nobody said what one weighs."""
    listing = publish_listing(alice, category_ids["Ajwa"], unit="kg")
    assert listing["price_per_gram"] is not None

    response = alice.patch(
        f"/api/listings/{listing['id']}",
        data={"price": "25.00", "quantity": "1", "unit": "piece"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["price_per_gram"] is None


def test_owner_can_edit_shop_details(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """Shop name, contact number and location all update together."""
    listing = publish_listing(alice, category_ids["Ajwa"])

    response = alice.patch(
        f"/api/listings/{listing['id']}",
        data={
            "shop_name": "Karim Dates House",
            "contact_number": "01999888777",
            "shop_location": "Dhanmondi, Dhaka",
        },
    )

    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["shop_name"] == "Karim Dates House"
    assert updated["contact_number"] == "01999888777"
    assert updated["shop_location"] == "Dhanmondi, Dhaka"


def test_edit_changes_only_what_was_sent(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """A partial edit leaves every other field exactly as it was."""
    listing = publish_listing(
        alice,
        category_ids["Ajwa"],
        price="800.00",
        unit="kg",
        shop_name="Rahim Dates Shop",
        shop_location="Mirpur, Dhaka",
    )

    response = alice.patch(f"/api/listings/{listing['id']}", data={"price": "850.00"})

    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["price"] == "850.00"
    for field in (
        "category",
        "quantity",
        "unit",
        "shop_name",
        "contact_number",
        "shop_location",
        "status",
        "image_url",
        "posted_by",
        "created_at",
    ):
        assert updated[field] == listing[field], f"{field} should not have changed"


def test_edit_tidies_whitespace_in_text(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """The same cleaning as publishing: trimmed, and inner runs collapsed."""
    listing = publish_listing(alice, category_ids["Ajwa"])

    response = alice.patch(
        f"/api/listings/{listing['id']}",
        data={"shop_name": "   Rahim    Dates   Shop  "},
    )

    assert response.status_code == 200, response.text
    assert response.json()["shop_name"] == "Rahim Dates Shop"


def test_owner_can_move_listing_to_a_new_user_category(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """A listing can be moved to a variety that did not exist a moment ago.

    The new variety is created through ``POST /api/categories`` first, which is
    where name normalisation and duplicate prevention live, and the id it returns
    is what the edit uses.
    """
    listing = publish_listing(alice, category_ids["Ajwa"])

    created = alice.post("/api/categories", json={"name": "  barhi "})
    assert created.status_code == 201, created.text
    new_category = created.json()
    assert new_category["name"] == "Barhi", "the name should be normalised"
    assert new_category["source"] == "USER"

    response = alice.patch(
        f"/api/listings/{listing['id']}", data={"category_id": new_category["id"]}
    )

    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["id"] == listing["id"]
    assert updated["category"]["name"] == "Barhi"
    assert updated["category"]["source"] == "USER"


def test_edit_moves_updated_at_but_not_created_at(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """``created_at`` records when it was published; ``updated_at`` moves on."""
    listing = publish_listing(alice, category_ids["Ajwa"])

    response = alice.patch(f"/api/listings/{listing['id']}", data={"price": "999.00"})

    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["created_at"] == listing["created_at"]
    assert updated["updated_at"] >= listing["updated_at"]


def test_edit_does_not_create_a_second_listing(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """After three edits there is still exactly one listing."""
    listing = publish_listing(alice, category_ids["Ajwa"])

    for price in ("810.00", "820.00", "830.00"):
        assert (
            alice.patch(
                f"/api/listings/{listing['id']}", data={"price": price}
            ).status_code
            == 200
        )

    mine = alice.get("/api/listings/mine").json()
    assert mine["count"] == 1
    assert mine["listings"][0]["id"] == listing["id"]
    assert mine["listings"][0]["price"] == "830.00"


# ===========================================================================
# Editing - the image
# ===========================================================================
def test_owner_can_replace_the_image(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """A new photo replaces the old one, and the old file is removed from disk."""
    listing = publish_listing(alice, category_ids["Ajwa"], colour="red")
    old_file = image_file_for(listing)
    assert old_file.is_file(), "the published photo should be on disk"

    response = alice.patch(
        f"/api/listings/{listing['id']}", files=image_upload(colour="blue")
    )

    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["id"] == listing["id"]
    assert updated["image_url"] != listing["image_url"]

    new_file = image_file_for(updated)
    assert new_file.is_file(), "the replacement photo should be on disk"
    assert not old_file.exists(), "the replaced photo should have been deleted"


def test_image_and_fields_can_be_replaced_in_one_request(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """One request can change the photo and the price together."""
    listing = publish_listing(alice, category_ids["Ajwa"], price="800.00")

    response = alice.patch(
        f"/api/listings/{listing['id']}",
        data={"price": "925.50"},
        files=image_upload(colour="green"),
    )

    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["price"] == "925.50"
    assert updated["image_url"] != listing["image_url"]
    assert not image_file_for(listing).exists()


def test_editing_other_fields_keeps_the_image(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """An edit that sends no photo must not disturb the existing one."""
    listing = publish_listing(alice, category_ids["Ajwa"])
    original_file = image_file_for(listing)

    response = alice.patch(f"/api/listings/{listing['id']}", data={"price": "777.00"})

    assert response.status_code == 200, response.text
    assert response.json()["image_url"] == listing["image_url"]
    assert original_file.is_file(), "the photo should still be there"


def test_empty_image_field_means_keep_the_current_photo(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """A file input with nothing chosen must not be read as a broken upload.

    A browser submitting an untouched file input sends the field anyway, with no
    filename. That means "I did not pick a new photo", so it has to be ignored
    rather than answered with a validation error.
    """
    listing = publish_listing(alice, category_ids["Ajwa"])

    response = alice.patch(
        f"/api/listings/{listing['id']}",
        data={"price": "801.00"},
        files={"image": ("", b"", "application/octet-stream")},
    )

    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["price"] == "801.00"
    assert updated["image_url"] == listing["image_url"]
    assert image_file_for(listing).is_file()


def test_empty_image_field_alone_is_not_a_change(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """An empty photo field and nothing else still counts as "nothing to change"."""
    listing = publish_listing(alice, category_ids["Ajwa"])

    response = alice.patch(
        f"/api/listings/{listing['id']}",
        files={"image": ("", b"", "application/octet-stream")},
    )

    assert response.status_code == 400, response.text


def test_edit_rejects_a_file_that_is_not_an_image(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """A .jpg containing rubbish is refused, and the listing is untouched."""
    listing = publish_listing(alice, category_ids["Ajwa"])

    response = alice.patch(
        f"/api/listings/{listing['id']}",
        files={"image": ("fake.jpg", b"this is definitely not a JPEG", "image/jpeg")},
    )

    assert response.status_code == 400, response.text
    assert "image" in response.json()["detail"].lower()
    # The original photo and price survived the failed edit.
    assert image_file_for(listing).is_file()
    assert alice.get(f"/api/listings/{listing['id']}").json() == listing


def test_edit_rejects_an_unsupported_file_type(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """A text file is refused by type, before anything is decoded."""
    listing = publish_listing(alice, category_ids["Ajwa"])

    response = alice.patch(
        f"/api/listings/{listing['id']}",
        files={"image": ("notes.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 415, response.text


def test_edit_rejects_an_oversized_image(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """Over the 5 MB limit is refused before the bytes are decoded."""
    listing = publish_listing(alice, category_ids["Ajwa"])
    too_big = b"\xff" * (settings.max_upload_bytes + 1)

    response = alice.patch(
        f"/api/listings/{listing['id']}",
        files={"image": ("huge.jpg", too_big, "image/jpeg")},
    )

    assert response.status_code == 413, response.text
    assert image_file_for(listing).is_file()


# ===========================================================================
# Editing - what must be refused
# ===========================================================================
def test_edit_with_nothing_to_change_is_400(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """An empty edit is answered clearly instead of pretending to succeed."""
    listing = publish_listing(alice, category_ids["Ajwa"])

    response = alice.patch(f"/api/listings/{listing['id']}", data={})

    assert response.status_code == 400, response.text
    assert "nothing to change" in response.json()["detail"].lower()


def test_edit_with_an_unknown_category_is_404(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """An id that matches no category is a clear 404, not a database error."""
    listing = publish_listing(alice, category_ids["Ajwa"])

    response = alice.patch(
        f"/api/listings/{listing['id']}", data={"category_id": 999_999}
    )

    assert response.status_code == 404, response.text
    assert "categor" in response.json()["detail"].lower()
    # Nothing changed.
    assert alice.get(f"/api/listings/{listing['id']}").json() == listing


def test_edit_of_an_unknown_listing_is_404(alice: ApiUser) -> None:
    response = alice.patch("/api/listings/999999", data={"price": "100.00"})
    assert response.status_code == 404, response.text


def test_edit_rejects_a_price_of_zero(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """The same rule as publishing: a price must be greater than zero."""
    listing = publish_listing(alice, category_ids["Ajwa"])

    response = alice.patch(f"/api/listings/{listing['id']}", data={"price": "0"})

    assert response.status_code == 422, response.text


def test_edit_rejects_a_blank_shop_name(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """Whitespace is not a shop name, even though it has a length."""
    listing = publish_listing(alice, category_ids["Ajwa"])

    response = alice.patch(f"/api/listings/{listing['id']}", data={"shop_name": "    "})

    assert response.status_code == 422, response.text


def test_edit_rejects_an_implausible_contact_number(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    listing = publish_listing(alice, category_ids["Ajwa"])

    response = alice.patch(
        f"/api/listings/{listing['id']}", data={"contact_number": "12"}
    )

    assert response.status_code == 422, response.text


def test_edit_cannot_reassign_the_owner_or_the_status(
    alice: ApiUser, bob: ApiUser, category_ids: dict[str, int]
) -> None:
    """Fields the edit form does not declare are ignored, not obeyed.

    ``user_id`` would hand the listing to somebody else, and ``status`` would hide
    it. Neither is part of the form, so both are dropped - the price still
    changes, and nothing else does.
    """
    listing = publish_listing(alice, category_ids["Ajwa"])

    response = alice.patch(
        f"/api/listings/{listing['id']}",
        data={"price": "888.00", "user_id": bob.id, "status": "INACTIVE"},
    )

    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["price"] == "888.00"
    assert updated["posted_by"]["id"] == alice.id
    assert updated["status"] == "ACTIVE"


# ===========================================================================
# Editing - ownership
# ===========================================================================
def test_non_owner_cannot_edit(
    alice: ApiUser, bob: ApiUser, category_ids: dict[str, int]
) -> None:
    """Bob is refused, and Alice's listing is untouched.

    This is the check the whole ownership requirement rests on. Bob is sending the
    request directly, exactly as anyone could, so hiding the Edit button in React
    would make no difference here.
    """
    listing = publish_listing(alice, category_ids["Ajwa"], price="800.00")

    response = bob.patch(f"/api/listings/{listing['id']}", data={"price": "1.00"})

    assert response.status_code == 403, response.text
    assert alice.get(f"/api/listings/{listing['id']}").json()["price"] == "800.00"


def test_non_owner_cannot_replace_the_image(
    alice: ApiUser, bob: ApiUser, category_ids: dict[str, int]
) -> None:
    """A refused edit must not have written or deleted any file."""
    listing = publish_listing(alice, category_ids["Ajwa"])
    original_file = image_file_for(listing)

    response = bob.patch(
        f"/api/listings/{listing['id']}", files=image_upload(colour="black")
    )

    assert response.status_code == 403, response.text
    assert original_file.is_file()
    assert alice.get(f"/api/listings/{listing['id']}").json()["image_url"] == (
        listing["image_url"]
    )


def test_edit_requires_a_login(
    client: TestClient, alice: ApiUser, category_ids: dict[str, int]
) -> None:
    listing = publish_listing(alice, category_ids["Ajwa"])

    response = client.patch(
        f"/api/listings/{listing['id']}", data={"price": "100.00"}
    )

    assert response.status_code == 401, response.text


# ===========================================================================
# Deactivating
# ===========================================================================
def test_owner_can_deactivate(alice: ApiUser, category_ids: dict[str, int]) -> None:
    listing = publish_listing(alice, category_ids["Ajwa"])

    response = alice.post(f"/api/listings/{listing['id']}/deactivate")

    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["id"] == listing["id"]
    assert updated["status"] == "INACTIVE"


def test_deactivating_keeps_the_row_and_the_photo(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """Deactivating is not deleting - the listing and its file both survive.

    The photo has to stay, because the listing can be switched back on later and
    would otherwise come back with a broken image.
    """
    listing = publish_listing(alice, category_ids["Ajwa"])
    photo = image_file_for(listing)

    assert alice.post(f"/api/listings/{listing['id']}/deactivate").status_code == 200

    still_there = alice.get(f"/api/listings/{listing['id']}")
    assert still_there.status_code == 200
    assert still_there.json()["image_url"] == listing["image_url"]
    assert photo.is_file(), "an inactive listing must keep its photo"


def test_deactivating_twice_is_not_an_error(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """The second click asks for a state it is already in, so nothing happens."""
    listing = publish_listing(alice, category_ids["Ajwa"])

    first = alice.post(f"/api/listings/{listing['id']}/deactivate")
    second = alice.post(f"/api/listings/{listing['id']}/deactivate")

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "INACTIVE"
    # Nothing was written, so the modification time did not move.
    assert second.json()["updated_at"] == first.json()["updated_at"]


def test_inactive_listing_is_hidden_from_other_users(
    alice: ApiUser, bob: ApiUser, category_ids: dict[str, int]
) -> None:
    """Bob could see it while it was active, and cannot once it is not.

    404 rather than 403: a deactivated listing is meant to be hidden, and "you are
    not allowed to see this" would confirm that it exists.
    """
    listing = publish_listing(alice, category_ids["Ajwa"])
    assert bob.get(f"/api/listings/{listing['id']}").status_code == 200

    alice.post(f"/api/listings/{listing['id']}/deactivate")

    assert bob.get(f"/api/listings/{listing['id']}").status_code == 404


def test_inactive_listing_stays_in_my_listings(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """The author keeps seeing it - this is where it is reactivated from."""
    listing = publish_listing(alice, category_ids["Ajwa"])
    alice.post(f"/api/listings/{listing['id']}/deactivate")

    mine = alice.get("/api/listings/mine").json()

    assert mine["count"] == 1
    assert mine["listings"][0]["id"] == listing["id"]
    assert mine["listings"][0]["status"] == "INACTIVE"


def test_non_owner_cannot_deactivate(
    alice: ApiUser, bob: ApiUser, category_ids: dict[str, int]
) -> None:
    listing = publish_listing(alice, category_ids["Ajwa"])

    response = bob.post(f"/api/listings/{listing['id']}/deactivate")

    assert response.status_code == 403, response.text
    assert alice.get(f"/api/listings/{listing['id']}").json()["status"] == "ACTIVE"


def test_deactivate_requires_a_login(
    client: TestClient, alice: ApiUser, category_ids: dict[str, int]
) -> None:
    listing = publish_listing(alice, category_ids["Ajwa"])
    assert client.post(f"/api/listings/{listing['id']}/deactivate").status_code == 401


def test_deactivate_of_an_unknown_listing_is_404(alice: ApiUser) -> None:
    assert alice.post("/api/listings/999999/deactivate").status_code == 404


# ===========================================================================
# Reactivating
# ===========================================================================
def test_owner_can_reactivate(alice: ApiUser, category_ids: dict[str, int]) -> None:
    listing = publish_listing(alice, category_ids["Ajwa"])
    alice.post(f"/api/listings/{listing['id']}/deactivate")

    response = alice.post(f"/api/listings/{listing['id']}/reactivate")

    assert response.status_code == 200, response.text
    assert response.json()["id"] == listing["id"]
    assert response.json()["status"] == "ACTIVE"


def test_reactivated_listing_is_visible_to_others_again(
    alice: ApiUser, bob: ApiUser, category_ids: dict[str, int]
) -> None:
    """Hidden, then shown again - the full round trip."""
    listing = publish_listing(alice, category_ids["Ajwa"])

    alice.post(f"/api/listings/{listing['id']}/deactivate")
    assert bob.get(f"/api/listings/{listing['id']}").status_code == 404

    alice.post(f"/api/listings/{listing['id']}/reactivate")
    seen = bob.get(f"/api/listings/{listing['id']}")

    assert seen.status_code == 200, seen.text
    assert seen.json()["status"] == "ACTIVE"
    assert seen.json()["image_url"] == listing["image_url"]


def test_reactivating_twice_is_not_an_error(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """A new listing is already ACTIVE, so reactivating it changes nothing."""
    listing = publish_listing(alice, category_ids["Ajwa"])

    response = alice.post(f"/api/listings/{listing['id']}/reactivate")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ACTIVE"
    assert response.json()["updated_at"] == listing["updated_at"]


def test_non_owner_cannot_reactivate(
    alice: ApiUser, bob: ApiUser, category_ids: dict[str, int]
) -> None:
    listing = publish_listing(alice, category_ids["Ajwa"])
    alice.post(f"/api/listings/{listing['id']}/deactivate")

    response = bob.post(f"/api/listings/{listing['id']}/reactivate")

    assert response.status_code == 403, response.text


def test_a_hidden_listing_can_be_edited_and_comes_back_at_the_new_price(
    alice: ApiUser, bob: ApiUser, category_ids: dict[str, int]
) -> None:
    """Deactivate, correct the price out of sight, then go live again.

    This is the realistic sequence - sold out, restock at a different price - and
    it checks that reactivating publishes the *current* details rather than the
    ones the listing had when it was hidden.
    """
    listing = publish_listing(alice, category_ids["Ajwa"], price="800.00", unit="kg")

    alice.post(f"/api/listings/{listing['id']}/deactivate")

    edited = alice.patch(f"/api/listings/{listing['id']}", data={"price": "950.00"})
    assert edited.status_code == 200, edited.text
    assert edited.json()["status"] == "INACTIVE", "editing must not un-hide it"
    assert bob.get(f"/api/listings/{listing['id']}").status_code == 404

    alice.post(f"/api/listings/{listing['id']}/reactivate")

    seen = bob.get(f"/api/listings/{listing['id']}")
    assert seen.status_code == 200, seen.text
    assert seen.json()["price"] == "950.00"
    assert float(seen.json()["price_per_gram"]) == 0.95


def test_deactivating_does_not_affect_another_users_listing(
    alice: ApiUser, bob: ApiUser, category_ids: dict[str, int]
) -> None:
    """Two listings in the same category; hiding one leaves the other alone."""
    alice_listing = publish_listing(alice, category_ids["Ajwa"], price="800.00")
    bob_listing = publish_listing(bob, category_ids["Ajwa"], price="750.00")

    alice.post(f"/api/listings/{alice_listing['id']}/deactivate")

    assert alice.get(f"/api/listings/{bob_listing['id']}").json()["status"] == "ACTIVE"
    assert image_file_for(bob_listing).is_file()


def test_replacing_an_image_leaves_other_listings_photos_alone(
    alice: ApiUser, bob: ApiUser, category_ids: dict[str, int]
) -> None:
    """Deleting a replaced photo must never touch a file another listing uses."""
    alice_listing = publish_listing(alice, category_ids["Ajwa"])
    bob_listing = publish_listing(bob, category_ids["Ajwa"])
    bob_photo = image_file_for(bob_listing)

    response = alice.patch(
        f"/api/listings/{alice_listing['id']}", files=image_upload(colour="white")
    )

    assert response.status_code == 200, response.text
    assert bob_photo.is_file(), "another user's photo must survive"


def test_replacement_image_format_comes_from_the_content(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """A PNG named ".jpg" is stored as a .png, because the bytes decide.

    The name a browser sends is never trusted - not for the path, and not for the
    format.
    """
    import io

    from PIL import Image

    listing = publish_listing(alice, category_ids["Ajwa"])

    buffer = io.BytesIO()
    Image.new("RGB", (20, 20), "purple").save(buffer, format="PNG")

    response = alice.patch(
        f"/api/listings/{listing['id']}",
        files={"image": ("misnamed.jpg", buffer.getvalue(), "image/jpeg")},
    )

    assert response.status_code == 200, response.text
    assert response.json()["image_url"].endswith(".png")
    assert image_file_for(response.json()).is_file()


def test_published_image_is_served_over_http(
    alice: ApiUser, client: TestClient, category_ids: dict[str, int]
) -> None:
    """The photo of a listing is actually fetchable at its image_url.

    Included here because image replacement is only really working if the *new*
    file can be loaded by a browser, not merely recorded in the database.
    """
    listing = publish_listing(alice, category_ids["Ajwa"])
    replaced = alice.patch(
        f"/api/listings/{listing['id']}", files=image_upload(colour="orange")
    ).json()

    response = client.get(replaced["image_url"])

    assert response.status_code == 200, response.text
    assert response.content == make_image_bytes("orange")

"""PHASE 9 - the shared marketplace.

The three promises being checked
-------------------------------
**Everyone sees everyone.** The marketplace is not filtered by who is asking. If
two users each publish an Ajwa listing, both of them see both offers. This is the
requirement the whole application is built around, and the easiest one to break by
adding a well-meaning ``where user_id = me``.

**Only ACTIVE listings are public.** A deactivated listing vanishes from the
marketplace for everybody, and stops counting towards the best price.

**Cheapest means cheapest.** Tk180 for a 200 g packet is a smaller number than
Tk800 for a kilo, but it is the dearer fruit. The "best price" answer has to
compare per gram, or it recommends the wrong shop.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.listing import Listing
from tests.conftest import ApiUser, publish_listing


def ids_of(response_json: dict) -> list[int]:
    return [item["id"] for item in response_json["listings"]]


# ===========================================================================
# Shared visibility
# ===========================================================================
def test_every_user_sees_every_active_listing(
    alice: ApiUser, bob: ApiUser, category_ids: dict[str, int]
) -> None:
    """Alice sees Bob's offer and Bob sees Alice's - the core requirement."""
    alice_listing = publish_listing(
        alice, category_ids["Ajwa"], price="800.00", shop_name="Rahim Dates Shop"
    )
    bob_listing = publish_listing(
        bob, category_ids["Ajwa"], price="750.00", shop_name="Karim Dates Shop"
    )

    seen_by_alice = alice.get("/api/marketplace/listings").json()
    seen_by_bob = bob.get("/api/marketplace/listings").json()

    for view in (seen_by_alice, seen_by_bob):
        assert alice_listing["id"] in ids_of(view)
        assert bob_listing["id"] in ids_of(view)


def test_listings_carry_the_other_users_shop_details(
    alice: ApiUser, bob: ApiUser, category_ids: dict[str, int]
) -> None:
    """A card shows whose offer it is, and how to contact that shop."""
    publish_listing(
        bob,
        category_ids["Ajwa"],
        price="750.00",
        shop_name="Karim Dates Shop",
        contact_number="01999888777",
        shop_location="Mirpur, Dhaka",
    )

    listings = alice.get("/api/marketplace/listings").json()["listings"]
    card = next(item for item in listings if item["shop_name"] == "Karim Dates Shop")

    assert card["posted_by"]["name"] == bob.name
    assert card["posted_by"]["id"] == bob.id
    assert card["contact_number"] == "01999888777"
    assert card["shop_location"] == "Mirpur, Dhaka"
    assert card["image_url"].startswith("/uploads/listings/")
    assert card["category"]["name"] == "Ajwa"


def test_each_card_carries_its_own_image(
    alice: ApiUser, bob: ApiUser, category_ids: dict[str, int]
) -> None:
    """Photos must not be shared or shuffled between listings."""
    first = publish_listing(alice, category_ids["Ajwa"], price="800.00")
    second = publish_listing(bob, category_ids["Ajwa"], price="750.00")

    by_id = {
        item["id"]: item
        for item in alice.get("/api/marketplace/listings").json()["listings"]
    }

    assert by_id[first["id"]]["image_url"] == first["image_url"]
    assert by_id[second["id"]]["image_url"] == second["image_url"]
    assert first["image_url"] != second["image_url"]


def test_marketplace_requires_a_login(client: TestClient) -> None:
    assert client.get("/api/marketplace/listings").status_code == 401
    assert client.get("/api/marketplace/best-price?category_id=1").status_code == 401


# ===========================================================================
# Only ACTIVE listings are public
# ===========================================================================
def test_deactivated_listings_disappear_for_everyone(
    alice: ApiUser, bob: ApiUser, category_ids: dict[str, int]
) -> None:
    """Including for their own author, who sees them under My Listings instead."""
    listing = publish_listing(alice, category_ids["Ajwa"])
    assert listing["id"] in ids_of(bob.get("/api/marketplace/listings").json())

    alice.post(f"/api/listings/{listing['id']}/deactivate")

    assert listing["id"] not in ids_of(bob.get("/api/marketplace/listings").json())
    assert listing["id"] not in ids_of(alice.get("/api/marketplace/listings").json())
    # Still the author's, still there, just not public.
    assert listing["id"] in ids_of(alice.get("/api/listings/mine").json())


def test_reactivated_listings_come_back(
    alice: ApiUser, bob: ApiUser, category_ids: dict[str, int]
) -> None:
    listing = publish_listing(alice, category_ids["Ajwa"])
    alice.post(f"/api/listings/{listing['id']}/deactivate")
    alice.post(f"/api/listings/{listing['id']}/reactivate")

    assert listing["id"] in ids_of(bob.get("/api/marketplace/listings").json())


def test_total_counts_only_active_listings(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """The reported total must not include hidden listings."""
    publish_listing(alice, category_ids["Ajwa"], price="800.00")
    hidden = publish_listing(alice, category_ids["Ajwa"], price="700.00")

    before = alice.get(f"/api/marketplace/listings?category_id={category_ids['Ajwa']}")
    assert before.json()["total"] == 2

    alice.post(f"/api/listings/{hidden['id']}/deactivate")

    after = alice.get(f"/api/marketplace/listings?category_id={category_ids['Ajwa']}")
    assert after.json()["total"] == 1
    assert after.json()["count"] == 1


# ===========================================================================
# Category filter
# ===========================================================================
def test_category_filter_narrows_to_one_variety(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    ajwa = publish_listing(alice, category_ids["Ajwa"], price="800.00")
    medjool = publish_listing(alice, category_ids["Medjool"], price="900.00")

    filtered = alice.get(
        f"/api/marketplace/listings?category_id={category_ids['Ajwa']}"
    ).json()

    assert ids_of(filtered) == [ajwa["id"]]
    assert medjool["id"] not in ids_of(filtered)
    # The filter is echoed back so the interface can label the list.
    assert filtered["category"]["name"] == "Ajwa"


def test_no_filter_returns_every_variety(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    ajwa = publish_listing(alice, category_ids["Ajwa"], price="800.00")
    medjool = publish_listing(alice, category_ids["Medjool"], price="900.00")

    everything = alice.get("/api/marketplace/listings").json()

    assert everything["category"] is None
    assert {ajwa["id"], medjool["id"]} <= set(ids_of(everything))


def test_filtering_by_a_user_created_category(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """A variety added by a user works in the filter just like the built-in nine."""
    created = alice.post("/api/categories", json={"name": "Barhi"}).json()
    listing = publish_listing(alice, created["id"], price="600.00")

    filtered = alice.get(
        f"/api/marketplace/listings?category_id={created['id']}"
    ).json()

    assert ids_of(filtered) == [listing["id"]]
    assert filtered["category"]["source"] == "USER"


def test_unknown_category_is_404_not_an_empty_list(alice: ApiUser) -> None:
    """"That variety does not exist" and "nothing for sale" are different answers."""
    response = alice.get("/api/marketplace/listings?category_id=999999")

    assert response.status_code == 404, response.text
    assert "categor" in response.json()["detail"].lower()


def test_a_category_with_nothing_for_sale_is_an_empty_list(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    response = alice.get(
        f"/api/marketplace/listings?category_id={category_ids['Shaishe']}"
    )

    assert response.status_code == 200, response.text
    assert response.json()["total"] == 0
    assert response.json()["listings"] == []


# ===========================================================================
# Sorting
# ===========================================================================
def test_default_sort_is_cheapest_price_first(
    alice: ApiUser, bob: ApiUser, category_ids: dict[str, int]
) -> None:
    """Tk750, Tk800, Tk850 - exactly the order the specification asks for."""
    dearest = publish_listing(alice, category_ids["Ajwa"], price="850.00", unit="kg")
    middle = publish_listing(bob, category_ids["Ajwa"], price="800.00", unit="kg")
    cheapest = publish_listing(alice, category_ids["Ajwa"], price="750.00", unit="kg")

    listings = alice.get(
        f"/api/marketplace/listings?category_id={category_ids['Ajwa']}"
    ).json()

    assert ids_of(listings) == [cheapest["id"], middle["id"], dearest["id"]]
    assert [item["price"] for item in listings["listings"]] == [
        "750.00",
        "800.00",
        "850.00",
    ]
    assert listings["sort"] == "price"


def test_cards_keep_the_sellers_own_unit(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """Sorting by grams must not rewrite what the seller published."""
    publish_listing(
        alice, category_ids["Ajwa"], price="180.00", quantity="200", unit="gram"
    )

    card = alice.get(
        f"/api/marketplace/listings?category_id={category_ids['Ajwa']}"
        "&sort=price_per_gram"
    ).json()["listings"][0]

    assert card["price"] == "180.00"
    assert card["unit"] == "gram"
    assert float(card["quantity"]) == 200
    # The comparable figure travels alongside, it does not replace anything.
    assert Decimal(card["price_per_gram"]) == Decimal("0.90")


def test_price_per_gram_sort_ranks_by_real_value(
    alice: ApiUser, bob: ApiUser, category_ids: dict[str, int]
) -> None:
    """The case where the two sorts disagree, and per-gram is the right answer.

    Tk180 for 200 g is Tk0.90 a gram; Tk800 for 1 kg is Tk0.80 a gram. Sorted by
    the price on the card the packet comes first; sorted by value the kilo does.
    Both orderings are correct for what they claim to be, which is exactly why the
    choice has to be explicit.
    """
    packet = publish_listing(
        alice, category_ids["Ajwa"], price="180.00", quantity="200", unit="gram"
    )
    kilo = publish_listing(bob, category_ids["Ajwa"], price="800.00", unit="kg")

    by_card_price = alice.get(
        f"/api/marketplace/listings?category_id={category_ids['Ajwa']}&sort=price"
    ).json()
    by_value = alice.get(
        f"/api/marketplace/listings?category_id={category_ids['Ajwa']}"
        "&sort=price_per_gram"
    ).json()

    assert ids_of(by_card_price) == [packet["id"], kilo["id"]]
    assert ids_of(by_value) == [kilo["id"], packet["id"]]


def test_piece_listings_sort_last_by_value_but_are_not_dropped(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """A piece has no per-gram price, so it goes to the end - it does not vanish.

    This is the check that catches a missing NULLS LAST: PostgreSQL puts NULLs
    first on an ascending sort by default, which would park every uncomparable
    listing at the top of a "cheapest first" list.
    """
    per_piece = publish_listing(
        alice, category_ids["Ajwa"], price="25.00", unit="piece"
    )
    per_kilo = publish_listing(alice, category_ids["Ajwa"], price="800.00", unit="kg")

    listings = alice.get(
        f"/api/marketplace/listings?category_id={category_ids['Ajwa']}"
        "&sort=price_per_gram"
    ).json()

    assert ids_of(listings) == [per_kilo["id"], per_piece["id"]]
    assert listings["listings"][-1]["price_per_gram"] is None


def test_an_invalid_sort_is_refused(alice: ApiUser) -> None:
    response = alice.get("/api/marketplace/listings?sort=cheapest")
    assert response.status_code == 422, response.text


# ===========================================================================
# Paging
# ===========================================================================
def test_paging_reports_the_true_total(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """A truncated page must not look like the whole marketplace."""
    for price in ("700.00", "800.00", "900.00"):
        publish_listing(alice, category_ids["Ajwa"], price=price)

    page = alice.get(
        f"/api/marketplace/listings?category_id={category_ids['Ajwa']}&limit=2"
    ).json()

    assert page["count"] == 2
    assert page["total"] == 3, "total must describe every match, not just this page"


def test_paging_does_not_repeat_or_skip_listings(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """Three listings at the SAME price - the case a shaky sort order breaks.

    Without a unique tie-breaker, rows that tie on price can come back in a
    different order each query, so page two may repeat something from page one.
    """
    published = [
        publish_listing(alice, category_ids["Ajwa"], price="800.00")["id"]
        for _ in range(3)
    ]

    url = f"/api/marketplace/listings?category_id={category_ids['Ajwa']}&limit=2"
    first_page = ids_of(alice.get(url).json())
    second_page = ids_of(alice.get(f"{url}&offset=2").json())

    assert len(first_page) == 2
    assert len(second_page) == 1
    assert set(first_page) | set(second_page) == set(published)
    assert not set(first_page) & set(second_page), "pages must not overlap"


def test_page_size_limits_are_enforced(alice: ApiUser) -> None:
    assert alice.get("/api/marketplace/listings?limit=0").status_code == 422
    assert alice.get("/api/marketplace/listings?limit=201").status_code == 422
    assert alice.get("/api/marketplace/listings?offset=-1").status_code == 422


# ===========================================================================
# Best individual price
# ===========================================================================
def test_best_price_finds_the_cheapest_offer(
    alice: ApiUser, bob: ApiUser, category_ids: dict[str, int]
) -> None:
    """Tk750/kg from Karim Dates Shop beats Tk800/kg from Rahim's."""
    publish_listing(
        alice,
        category_ids["Ajwa"],
        price="800.00",
        unit="kg",
        shop_name="Rahim Dates Shop",
    )
    winner = publish_listing(
        bob,
        category_ids["Ajwa"],
        price="750.00",
        unit="kg",
        shop_name="Karim Dates Shop",
    )

    response = alice.get(
        f"/api/marketplace/best-price?category_id={category_ids['Ajwa']}"
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["category"]["name"] == "Ajwa"
    assert body["listing"]["id"] == winner["id"]
    assert body["listing"]["price"] == "750.00"
    assert body["listing"]["shop_name"] == "Karim Dates Shop"
    # The card needs the photo and the owner, so both must come back.
    assert body["listing"]["image_url"] == winner["image_url"]
    assert body["listing"]["posted_by"]["id"] == bob.id


def test_best_price_compares_per_gram_not_by_the_card_price(
    alice: ApiUser, bob: ApiUser, category_ids: dict[str, int]
) -> None:
    """The misleading case: the smaller number is the worse deal.

    Tk180 for a 200 g packet is Tk0.90 a gram. Tk800 for a kilo is Tk0.80 a gram.
    A "lowest price" query that looked only at the card would announce the packet
    and send the buyer to the more expensive shop.
    """
    publish_listing(
        alice,
        category_ids["Ajwa"],
        price="180.00",
        quantity="200",
        unit="gram",
        shop_name="Packet Shop",
    )
    better = publish_listing(
        bob, category_ids["Ajwa"], price="800.00", unit="kg", shop_name="Kilo Shop"
    )

    body = alice.get(
        f"/api/marketplace/best-price?category_id={category_ids['Ajwa']}"
    ).json()

    assert body["listing"]["id"] == better["id"]
    assert body["listing"]["shop_name"] == "Kilo Shop"
    assert Decimal(body["listing"]["price_per_gram"]) == Decimal("0.80")


def test_best_price_ignores_piece_listings(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """A piece cannot be weighed, so it cannot win a per-gram contest."""
    publish_listing(alice, category_ids["Ajwa"], price="5.00", unit="piece")
    comparable = publish_listing(
        alice, category_ids["Ajwa"], price="800.00", unit="kg"
    )

    body = alice.get(
        f"/api/marketplace/best-price?category_id={category_ids['Ajwa']}"
    ).json()

    assert body["listing"]["id"] == comparable["id"]


def test_best_price_says_so_when_only_piece_listings_exist(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """No comparable data is reported honestly, not as a price of zero."""
    publish_listing(alice, category_ids["Ajwa"], price="25.00", unit="piece")

    body = alice.get(
        f"/api/marketplace/best-price?category_id={category_ids['Ajwa']}"
    ).json()

    assert body["listing"] is None
    assert "no comparable price data" in body["message"].lower()


def test_best_price_says_so_when_nothing_is_for_sale(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    body = alice.get(
        f"/api/marketplace/best-price?category_id={category_ids['Sugaey']}"
    ).json()

    assert body["listing"] is None
    assert body["category"]["name"] == "Sugaey"


def test_best_price_ignores_deactivated_listings(
    alice: ApiUser, bob: ApiUser, category_ids: dict[str, int]
) -> None:
    """Hiding the cheapest offer promotes the next one."""
    cheapest = publish_listing(alice, category_ids["Ajwa"], price="700.00", unit="kg")
    runner_up = publish_listing(bob, category_ids["Ajwa"], price="800.00", unit="kg")

    url = f"/api/marketplace/best-price?category_id={category_ids['Ajwa']}"
    assert alice.get(url).json()["listing"]["id"] == cheapest["id"]

    alice.post(f"/api/listings/{cheapest['id']}/deactivate")

    assert alice.get(url).json()["listing"]["id"] == runner_up["id"]

    alice.post(f"/api/listings/{cheapest['id']}/reactivate")

    assert alice.get(url).json()["listing"]["id"] == cheapest["id"]


def test_best_price_follows_an_edit(
    alice: ApiUser, bob: ApiUser, category_ids: dict[str, int]
) -> None:
    """Editing a price changes who is cheapest, immediately.

    Nothing is cached, so there is no stale figure to invalidate - the answer is
    worked out from the current rows every time it is asked for.
    """
    alice_listing = publish_listing(
        alice, category_ids["Ajwa"], price="800.00", unit="kg"
    )
    bob_listing = publish_listing(bob, category_ids["Ajwa"], price="750.00", unit="kg")

    url = f"/api/marketplace/best-price?category_id={category_ids['Ajwa']}"
    assert alice.get(url).json()["listing"]["id"] == bob_listing["id"]

    alice.patch(f"/api/listings/{alice_listing['id']}", data={"price": "700.00"})

    assert alice.get(url).json()["listing"]["id"] == alice_listing["id"]


def test_best_price_follows_a_category_change(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """Moving the cheapest Ajwa to Medjool changes both categories' answers."""
    listing = publish_listing(alice, category_ids["Ajwa"], price="700.00", unit="kg")
    publish_listing(alice, category_ids["Ajwa"], price="900.00", unit="kg")

    ajwa_url = f"/api/marketplace/best-price?category_id={category_ids['Ajwa']}"
    medjool_url = f"/api/marketplace/best-price?category_id={category_ids['Medjool']}"

    assert alice.get(ajwa_url).json()["listing"]["id"] == listing["id"]
    assert alice.get(medjool_url).json()["listing"] is None

    alice.patch(
        f"/api/listings/{listing['id']}", data={"category_id": category_ids["Medjool"]}
    )

    assert alice.get(ajwa_url).json()["listing"]["price"] == "900.00"
    assert alice.get(medjool_url).json()["listing"]["id"] == listing["id"]


def test_best_price_requires_a_category(alice: ApiUser) -> None:
    assert alice.get("/api/marketplace/best-price").status_code == 422


def test_best_price_with_an_unknown_category_is_404(alice: ApiUser) -> None:
    assert (
        alice.get("/api/marketplace/best-price?category_id=999999").status_code == 404
    )


# ===========================================================================
# The per-gram rule is written twice - so check both agree
# ===========================================================================
def test_python_and_sql_agree_on_price_per_gram(
    alice: ApiUser, db: Session, category_ids: dict[str, int]
) -> None:
    """``price_per_gram`` exists as Python and as SQL; they must never disagree.

    The Python version fills in each listing's ``price_per_gram`` field, while the
    SQL version does the ordering inside the database. If one were changed without
    the other, the marketplace would present figures that contradicted its own sort
    order - so this compares them directly.

    The query goes through the test's own session on purpose. A fresh connection
    would sit outside this test's transaction, see none of the rows below, and pass
    by having nothing to check.
    """
    cases = [
        ("800.00", "1", "kg", Decimal("0.80")),
        ("180.00", "200", "gram", Decimal("0.90")),
        ("150.00", "150", "gram", Decimal("1.00")),
        ("1000.00", "2", "kg", Decimal("0.50")),
        ("25.00", "1", "piece", None),
    ]

    published_ids = []
    for price, quantity, unit, expected in cases:
        published = publish_listing(
            alice,
            category_ids["Ajwa"],
            price=price,
            quantity=quantity,
            unit=unit,
        )
        published_ids.append(published["id"])

        # 1. The Python property, as reported in the API response.
        from_python = published["price_per_gram"]
        assert (
            Decimal(from_python) if from_python is not None else None
        ) == expected, f"Python disagreed for {price}/{quantity}{unit}"

    # 2. The SQL expression, evaluated by PostgreSQL over those same rows.
    rows = db.execute(
        select(
            Listing.id,
            Listing.price,
            Listing.quantity,
            Listing.unit,
            Listing.price_per_gram,
        ).where(Listing.id.in_(published_ids))
    ).all()

    assert len(rows) == len(cases), "the comparison must actually have rows to check"

    for listing_id, price_value, quantity_value, unit_value, sql_value in rows:
        in_python = Listing(
            price=price_value, quantity=quantity_value, unit=unit_value
        ).price_per_gram
        assert in_python == sql_value, (
            f"listing {listing_id}: Python said {in_python}, SQL said {sql_value} "
            f"for {price_value} / {quantity_value} {unit_value}"
        )

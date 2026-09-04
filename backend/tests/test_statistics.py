"""PHASE 10 - price statistics.

The specification works three examples through by hand (sections 75, 76 and 77), and
those are written out below as tests with the same numbers, because a statistics
feature that is merely plausible is worthless - it has to be arithmetically right.

The four ways an average goes wrong
-----------------------------------
**Counting the wrong listings.** Only ACTIVE listings priced by gram or kg belong in
it. A deactivated listing or one priced per piece must not shift the figure.

**Averaging the wrong thing.** It is the mean of the per-gram prices, not a total
price divided by a total weight. Three listings count equally however much each is
selling.

**Reporting zero for "no data".** "Nobody sells this by weight" and "it is free" are
different answers, and a zero would sort an empty category to the top of a
cheapest-first list.

**Going stale.** Nothing is cached, so an edit, a deactivation or a category change
has to show up in the very next request.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from tests.conftest import ApiUser, publish_listing


def average_of(user: ApiUser, category_id: int) -> Decimal | None:
    body = user.get(f"/api/categories/{category_id}/stats").json()
    raw = body["average_price_per_gram"]
    return Decimal(raw) if raw is not None else None


def stats_of(user: ApiUser, category_id: int) -> dict:
    response = user.get(f"/api/categories/{category_id}/stats")
    assert response.status_code == 200, response.text
    return response.json()


# ===========================================================================
# The specification's own worked example (section 75)
# ===========================================================================
def test_specification_average_example(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """Section 75, step by step, with the specification's exact numbers.

        Tk800/kg, Tk900/kg, Tk1000/kg   ->  0.80, 0.90, 1.00   ->  average 0.90
        add Tk180 for 200 g             ->  0.90               ->  average 0.90
        add Tk20 per piece              ->  excluded           ->  average 0.90
    """
    ajwa = category_ids["Ajwa"]

    for price in ("800.00", "900.00", "1000.00"):
        publish_listing(alice, ajwa, price=price, unit="kg")

    # (0.80 + 0.90 + 1.00) / 3 = 0.90
    assert average_of(alice, ajwa) == Decimal("0.9000")
    assert stats_of(alice, ajwa)["listing_count"] == 3

    # Tk180 for a 200 g packet is also 0.90 a gram, so the mean does not move.
    publish_listing(alice, ajwa, price="180.00", quantity="200", unit="gram")

    # (0.80 + 0.90 + 1.00 + 0.90) / 4 = 0.90
    assert average_of(alice, ajwa) == Decimal("0.9000")
    assert stats_of(alice, ajwa)["listing_count"] == 4

    # A piece listing must not touch the gram-based average at all.
    publish_listing(alice, ajwa, price="20.00", unit="piece")

    assert average_of(alice, ajwa) == Decimal("0.9000")
    stats = stats_of(alice, ajwa)
    assert stats["listing_count"] == 4, "the piece listing must not be counted"
    assert stats["active_listing_count"] == 5
    assert stats["excluded_piece_count"] == 1


def test_specification_best_average_example(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """Section 76: Ajwa 0.90, Galaxy 1.20, Medjool 1.40, Rutab 0.75 -> Rutab wins."""
    # One listing each, priced so the per-gram average is exactly the target.
    publish_listing(alice, category_ids["Ajwa"], price="900.00", unit="kg")
    publish_listing(alice, category_ids["Galaxy"], price="1200.00", unit="kg")
    publish_listing(alice, category_ids["Medjool"], price="1400.00", unit="kg")
    publish_listing(alice, category_ids["Rutab"], price="750.00", unit="kg")

    body = alice.get("/api/categories/statistics").json()

    by_name = {item["category"]: item for item in body["categories"]}
    assert Decimal(by_name["Ajwa"]["average_price_per_gram"]) == Decimal("0.9000")
    assert Decimal(by_name["Galaxy"]["average_price_per_gram"]) == Decimal("1.2000")
    assert Decimal(by_name["Medjool"]["average_price_per_gram"]) == Decimal("1.4000")
    assert Decimal(by_name["Rutab"]["average_price_per_gram"]) == Decimal("0.7500")

    assert body["best_average_price"]["category"] == "Rutab"
    assert Decimal(body["best_average_price"]["average_price_per_gram"]) == Decimal(
        "0.7500"
    )


def test_specification_selected_category_example(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """Section 77: selecting Ajwa gives 0.90, selecting Rutab gives 0.75.

    The numbers come from the database, not from anything hard-coded - which is why
    they are published through the API first and then read back.
    """
    publish_listing(alice, category_ids["Ajwa"], price="800.00", unit="kg")
    publish_listing(alice, category_ids["Ajwa"], price="1000.00", unit="kg")
    publish_listing(alice, category_ids["Rutab"], price="750.00", unit="kg")

    assert average_of(alice, category_ids["Ajwa"]) == Decimal("0.9000")
    assert average_of(alice, category_ids["Rutab"]) == Decimal("0.7500")


# ===========================================================================
# The conversion rule
# ===========================================================================
def test_kg_is_converted_to_grams(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """Tk800 for 1 kg is Tk0.80 a gram, using 1 kg = 1000 g."""
    publish_listing(alice, category_ids["Ajwa"], price="800.00", quantity="1", unit="kg")
    assert average_of(alice, category_ids["Ajwa"]) == Decimal("0.8000")


def test_multi_kilo_and_part_gram_quantities(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """The quantity is part of the sum, not assumed to be 1."""
    ajwa = category_ids["Ajwa"]
    # Tk1000 for 2 kg = Tk0.50/g ; Tk150 for 150 g = Tk1.00/g. Mean = 0.75.
    publish_listing(alice, ajwa, price="1000.00", quantity="2", unit="kg")
    publish_listing(alice, ajwa, price="150.00", quantity="150", unit="gram")

    assert average_of(alice, ajwa) == Decimal("0.7500")


def test_average_is_the_mean_of_prices_not_a_total_over_a_total(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """A big cheap sack must not outvote a small dear packet.

    Tk1000 for 10 kg is Tk0.10/g; Tk100 for 100 g is Tk1.00/g.

        mean of the per-gram prices  =  (0.10 + 1.00) / 2  =  0.55   <- correct
        total money / total grams    =  1100 / 10100       =  0.1089 <- not this

    The specification asks for the arithmetic mean of the per-gram prices, so each
    listing carries equal weight regardless of how much fruit it is selling.
    """
    ajwa = category_ids["Ajwa"]
    publish_listing(alice, ajwa, price="1000.00", quantity="10", unit="kg")
    publish_listing(alice, ajwa, price="100.00", quantity="100", unit="gram")

    assert average_of(alice, ajwa) == Decimal("0.5500")


def test_average_is_reported_to_four_decimal_places(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """A recurring average is rounded, not truncated, and not flattened to 2 places.

    Tk800, Tk900 and Tk1000 per kg average to 0.90 exactly; make it Tk850 instead of
    Tk900 and the mean becomes 0.8833... which has to survive as something more
    precise than 0.88 for the cheapest-average comparison to stay meaningful.
    """
    ajwa = category_ids["Ajwa"]
    for price in ("800.00", "850.00", "1000.00"):
        publish_listing(alice, ajwa, price=price, unit="kg")

    # (0.80 + 0.85 + 1.00) / 3 = 0.883333...
    assert average_of(alice, ajwa) == Decimal("0.8833")


# ===========================================================================
# What must not count
# ===========================================================================
def test_piece_listings_are_excluded_entirely(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """A category sold only by the piece has no average - not an average of zero."""
    publish_listing(alice, category_ids["Ajwa"], price="25.00", unit="piece")
    publish_listing(alice, category_ids["Ajwa"], price="30.00", unit="piece")

    stats = stats_of(alice, category_ids["Ajwa"])

    assert stats["average_price_per_gram"] is None
    assert stats["listing_count"] == 0
    assert stats["active_listing_count"] == 2
    assert stats["excluded_piece_count"] == 2
    assert "no gram-based price data available" in stats["message"].lower()


def test_inactive_listings_are_excluded(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """Deactivating the cheap listing raises the average immediately."""
    ajwa = category_ids["Ajwa"]
    cheap = publish_listing(alice, ajwa, price="800.00", unit="kg")
    publish_listing(alice, ajwa, price="1000.00", unit="kg")

    assert average_of(alice, ajwa) == Decimal("0.9000")

    alice.post(f"/api/listings/{cheap['id']}/deactivate")

    assert average_of(alice, ajwa) == Decimal("1.0000")
    assert stats_of(alice, ajwa)["listing_count"] == 1
    assert stats_of(alice, ajwa)["active_listing_count"] == 1


def test_reactivating_brings_a_listing_back_into_the_average(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    ajwa = category_ids["Ajwa"]
    cheap = publish_listing(alice, ajwa, price="800.00", unit="kg")
    publish_listing(alice, ajwa, price="1000.00", unit="kg")

    alice.post(f"/api/listings/{cheap['id']}/deactivate")
    assert average_of(alice, ajwa) == Decimal("1.0000")

    alice.post(f"/api/listings/{cheap['id']}/reactivate")
    assert average_of(alice, ajwa) == Decimal("0.9000")


def test_another_categorys_listings_do_not_leak_in(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    publish_listing(alice, category_ids["Ajwa"], price="800.00", unit="kg")
    publish_listing(alice, category_ids["Medjool"], price="2000.00", unit="kg")

    assert average_of(alice, category_ids["Ajwa"]) == Decimal("0.8000")
    assert average_of(alice, category_ids["Medjool"]) == Decimal("2.0000")


def test_the_average_spans_all_users(
    alice: ApiUser, bob: ApiUser, category_ids: dict[str, int]
) -> None:
    """Statistics describe the shared marketplace, not one person's listings."""
    ajwa = category_ids["Ajwa"]
    publish_listing(alice, ajwa, price="800.00", unit="kg")
    publish_listing(bob, ajwa, price="1000.00", unit="kg")

    # Both users see the same figure, and it includes both listings.
    assert average_of(alice, ajwa) == Decimal("0.9000")
    assert average_of(bob, ajwa) == Decimal("0.9000")
    assert stats_of(bob, ajwa)["listing_count"] == 2


# ===========================================================================
# No data
# ===========================================================================
def test_a_category_with_nothing_for_sale_reports_null_not_zero(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """The single most important thing not to get wrong."""
    stats = stats_of(alice, category_ids["Shaishe"])

    assert stats["average_price_per_gram"] is None
    assert stats["average_price_per_gram"] != 0
    assert stats["listing_count"] == 0
    assert stats["active_listing_count"] == 0
    assert stats["message"].startswith("No gram-based price data available")


def test_a_new_user_category_starts_with_no_data(alice: ApiUser) -> None:
    created = alice.post("/api/categories", json={"name": "Barhi"}).json()

    stats = stats_of(alice, created["id"])

    assert stats["category"] == "Barhi"
    assert stats["category_source"] == "USER"
    assert stats["average_price_per_gram"] is None
    assert stats["listing_count"] == 0


def test_empty_categories_stay_out_of_the_global_list(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """And the totals explain where they went, instead of losing them silently."""
    publish_listing(alice, category_ids["Ajwa"], price="800.00", unit="kg")

    body = alice.get("/api/categories/statistics").json()

    names = [item["category"] for item in body["categories"]]
    assert names == ["Ajwa"]
    assert body["counted_categories"] == 1
    assert body["total_categories"] >= 9, "the other varieties still exist"


def test_global_statistics_with_no_data_at_all(alice: ApiUser) -> None:
    """Section 55's empty case: an empty list and a null winner."""
    body = alice.get("/api/categories/statistics").json()

    assert body["categories"] == []
    assert body["best_average_price"] is None
    assert body["counted_categories"] == 0


def test_a_category_with_only_piece_listings_cannot_win(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """Tk1 per piece is a tiny number, but it is not a per-gram price."""
    publish_listing(alice, category_ids["Galaxy"], price="1.00", unit="piece")
    publish_listing(alice, category_ids["Ajwa"], price="900.00", unit="kg")

    body = alice.get("/api/categories/statistics").json()

    assert [item["category"] for item in body["categories"]] == ["Ajwa"]
    assert body["best_average_price"]["category"] == "Ajwa"


# ===========================================================================
# Global statistics and the best average
# ===========================================================================
def test_global_list_is_ordered_cheapest_average_first(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    publish_listing(alice, category_ids["Medjool"], price="1400.00", unit="kg")
    publish_listing(alice, category_ids["Rutab"], price="750.00", unit="kg")
    publish_listing(alice, category_ids["Galaxy"], price="1200.00", unit="kg")

    body = alice.get("/api/categories/statistics").json()

    assert [item["category"] for item in body["categories"]] == [
        "Rutab",
        "Galaxy",
        "Medjool",
    ]


def test_best_average_is_always_the_first_entry(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """The response must not be able to contradict itself."""
    publish_listing(alice, category_ids["Medjool"], price="1400.00", unit="kg")
    publish_listing(alice, category_ids["Rutab"], price="750.00", unit="kg")

    body = alice.get("/api/categories/statistics").json()

    assert body["best_average_price"]["category"] == body["categories"][0]["category"]
    assert (
        body["best_average_price"]["average_price_per_gram"]
        == body["categories"][0]["average_price_per_gram"]
    )
    assert (
        body["best_average_price"]["listing_count"]
        == body["categories"][0]["listing_count"]
    )


def test_best_average_uses_averages_not_single_cheap_listings(
    alice: ApiUser, bob: ApiUser, category_ids: dict[str, int]
) -> None:
    """A category can hold the single cheapest listing and still lose on average.

    Ajwa has one very cheap listing and one very dear one, averaging 1.05.
    Rutab has two moderate ones, averaging 0.90. Rutab is cheaper on average even
    though the outright cheapest listing in the marketplace is an Ajwa.
    """
    publish_listing(alice, category_ids["Ajwa"], price="100.00", unit="kg")
    publish_listing(bob, category_ids["Ajwa"], price="2000.00", unit="kg")
    publish_listing(alice, category_ids["Rutab"], price="800.00", unit="kg")
    publish_listing(bob, category_ids["Rutab"], price="1000.00", unit="kg")

    body = alice.get("/api/categories/statistics").json()

    assert body["best_average_price"]["category"] == "Rutab"
    assert Decimal(body["best_average_price"]["average_price_per_gram"]) == Decimal(
        "0.9000"
    )

    # Meanwhile the cheapest single Ajwa listing is still the cheapest single offer.
    best_ajwa = alice.get(
        f"/api/marketplace/best-price?category_id={category_ids['Ajwa']}"
    ).json()
    assert best_ajwa["listing"]["price"] == "100.00"


def test_tied_averages_resolve_the_same_way_every_time(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """Two identical averages must not swap places between requests."""
    publish_listing(alice, category_ids["Rutab"], price="800.00", unit="kg")
    publish_listing(alice, category_ids["Ajwa"], price="800.00", unit="kg")

    winners = {
        alice.get("/api/categories/statistics").json()["best_average_price"]["category"]
        for _ in range(4)
    }

    assert len(winners) == 1, f"the winner changed between requests: {winners}"
    # Alphabetical is the documented tie-breaker.
    assert winners == {"Ajwa"}


# ===========================================================================
# Nothing is cached (sections 57 and 58)
# ===========================================================================
def test_editing_a_price_updates_the_average_immediately(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    ajwa = category_ids["Ajwa"]
    listing = publish_listing(alice, ajwa, price="800.00", unit="kg")
    publish_listing(alice, ajwa, price="1000.00", unit="kg")

    assert average_of(alice, ajwa) == Decimal("0.9000")

    alice.patch(f"/api/listings/{listing['id']}", data={"price": "950.00"})

    # (0.95 + 1.00) / 2 = 0.975
    assert average_of(alice, ajwa) == Decimal("0.9750")


def test_editing_the_unit_updates_the_average(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """Switching a listing to piece removes it from the average."""
    ajwa = category_ids["Ajwa"]
    listing = publish_listing(alice, ajwa, price="800.00", unit="kg")
    publish_listing(alice, ajwa, price="1000.00", unit="kg")

    assert average_of(alice, ajwa) == Decimal("0.9000")

    alice.patch(
        f"/api/listings/{listing['id']}",
        data={"price": "25.00", "quantity": "1", "unit": "piece"},
    )

    assert average_of(alice, ajwa) == Decimal("1.0000")
    assert stats_of(alice, ajwa)["excluded_piece_count"] == 1


def test_changing_a_category_updates_both_averages(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """Section 57's requirement: the old and the new category both change."""
    ajwa, medjool = category_ids["Ajwa"], category_ids["Medjool"]
    moving = publish_listing(alice, ajwa, price="800.00", unit="kg")
    publish_listing(alice, ajwa, price="1000.00", unit="kg")
    publish_listing(alice, medjool, price="2000.00", unit="kg")

    assert average_of(alice, ajwa) == Decimal("0.9000")
    assert average_of(alice, medjool) == Decimal("2.0000")

    alice.patch(f"/api/listings/{moving['id']}", data={"category_id": medjool})

    # Ajwa loses its cheap listing; Medjool gains it.
    assert average_of(alice, ajwa) == Decimal("1.0000")
    assert average_of(alice, medjool) == Decimal("1.4000")


def test_deactivating_can_change_which_category_is_cheapest(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    """Section 58, end to end."""
    rutab = publish_listing(alice, category_ids["Rutab"], price="750.00", unit="kg")
    publish_listing(alice, category_ids["Ajwa"], price="900.00", unit="kg")

    url = "/api/categories/statistics"
    assert alice.get(url).json()["best_average_price"]["category"] == "Rutab"

    alice.post(f"/api/listings/{rutab['id']}/deactivate")

    body = alice.get(url).json()
    assert body["best_average_price"]["category"] == "Ajwa"
    assert "Rutab" not in [item["category"] for item in body["categories"]]

    alice.post(f"/api/listings/{rutab['id']}/reactivate")

    assert alice.get(url).json()["best_average_price"]["category"] == "Rutab"


# ===========================================================================
# Access and errors
# ===========================================================================
def test_statistics_require_a_login(client: TestClient) -> None:
    assert client.get("/api/categories/statistics").status_code == 401
    assert client.get("/api/categories/1/stats").status_code == 401


def test_unknown_category_stats_is_404(alice: ApiUser) -> None:
    """"No such variety" must be distinguishable from "no prices yet"."""
    response = alice.get("/api/categories/999999/stats")

    assert response.status_code == 404, response.text
    assert "categor" in response.json()["detail"].lower()


def test_the_word_statistics_is_not_read_as_a_category_id(alice: ApiUser) -> None:
    """A fixed path segment must win over the variable one next to it."""
    response = alice.get("/api/categories/statistics")

    assert response.status_code == 200, response.text
    assert "categories" in response.json()


def test_selected_category_average_matches_the_global_list(
    alice: ApiUser, bob: ApiUser, category_ids: dict[str, int]
) -> None:
    """The two endpoints must never disagree about the same category."""
    publish_listing(alice, category_ids["Ajwa"], price="800.00", unit="kg")
    publish_listing(bob, category_ids["Ajwa"], price="180.00", quantity="200", unit="gram")
    publish_listing(alice, category_ids["Rutab"], price="750.00", unit="kg")
    publish_listing(alice, category_ids["Galaxy"], price="30.00", unit="piece")

    global_body = alice.get("/api/categories/statistics").json()
    from_global = {
        item["category"]: item["average_price_per_gram"]
        for item in global_body["categories"]
    }

    for name in ("Ajwa", "Rutab"):
        single = stats_of(alice, category_ids[name])
        assert single["average_price_per_gram"] == from_global[name], name
        assert single["listing_count"] == next(
            item["listing_count"]
            for item in global_body["categories"]
            if item["category"] == name
        )

    # Galaxy has only a piece listing, so it is absent globally but still answers
    # honestly when asked directly.
    assert "Galaxy" not in from_global
    galaxy = stats_of(alice, category_ids["Galaxy"])
    assert galaxy["average_price_per_gram"] is None
    assert galaxy["active_listing_count"] == 1

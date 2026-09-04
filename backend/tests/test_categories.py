"""PHASE 13 - the specification's category test list (section 74).

Covers: the 9 initial categories, creating a user category, duplicate
normalisation, and the list that fills the dropdown.

The idea being pinned down here is that **there is exactly one row per variety,
however it is typed.** Without normalisation the table fills up with ``medjool``,
``Medjool``, `` MEDJOOL `` and ``Medjool`` as four separate categories, and every
dropdown in the application becomes a mess. Two mechanisms prevent it, and both
are tested: Python decides the one spelling that gets stored, and a UNIQUE index
in PostgreSQL is what actually makes a duplicate impossible.

Note what a repeated name returns. Submitting one is deliberately **not** an
error - someone typing "Medjool" into the new-category box simply means they want
Medjool. The status code carries the distinction instead: 201 created a new row,
200 means "that already existed, here it is".
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.classes import load_class_names
from tests.conftest import ApiUser


# ---------------------------------------------------------------------------
# The list, and the 9 seeded varieties
# ---------------------------------------------------------------------------
def test_the_nine_model_varieties_are_seeded(alice: ApiUser) -> None:
    response = alice.get("/api/categories")

    assert response.status_code == 200, response.text
    body = response.json()
    model_names = {c["name"] for c in body["categories"] if c["source"] == "MODEL"}
    assert len(model_names) == 9, sorted(model_names)


def test_the_seeded_names_match_classes_json_exactly(alice: ApiUser) -> None:
    """The database and the model must agree on the spelling of every variety.

    ``model/classes.json`` is the source of truth. If a seeded name differed by
    so much as a capital letter, a prediction could not be matched to the
    category it belongs to.
    """
    from_model = set(load_class_names())
    from_api = {
        c["name"] for c in alice.get("/api/categories").json()["categories"]
        if c["source"] == "MODEL"
    }
    assert from_api == from_model


def test_the_list_reports_a_count_that_matches(alice: ApiUser) -> None:
    body = alice.get("/api/categories").json()
    assert body["count"] == len(body["categories"])


def test_every_entry_has_what_a_dropdown_needs(alice: ApiUser) -> None:
    for category in alice.get("/api/categories").json()["categories"]:
        assert {"id", "name", "source", "created_at"} <= set(category)
        assert category["source"] in ("MODEL", "USER")


def test_the_list_requires_a_login(client: TestClient) -> None:
    assert client.get("/api/categories").status_code == 401


def test_seeding_is_idempotent(alice: ApiUser) -> None:
    """Asking twice does not multiply the categories.

    The migration seeds these, and running it again must not duplicate them.
    Reading the list twice is the cheap end of that check; the real guarantee is
    the UNIQUE index, exercised by the duplicate tests below.
    """
    first = alice.get("/api/categories").json()["count"]
    second = alice.get("/api/categories").json()["count"]
    assert first == second


# ---------------------------------------------------------------------------
# Creating a category
# ---------------------------------------------------------------------------
def test_a_new_variety_is_created(alice: ApiUser) -> None:
    response = alice.post("/api/categories", json={"name": "Barhi"})

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Barhi"
    # USER, not MODEL: the AI cannot predict this one, and the interface needs to
    # be able to say so.
    assert body["source"] == "USER"
    assert body["id"] > 0


def test_creating_a_category_requires_a_login(client: TestClient) -> None:
    assert client.post("/api/categories", json={"name": "Barhi"}).status_code == 401


def test_the_new_variety_appears_in_the_dropdown_immediately(alice: ApiUser) -> None:
    before = alice.get("/api/categories").json()["count"]
    created = alice.post("/api/categories", json={"name": "Barhi"}).json()

    body = alice.get("/api/categories").json()
    assert body["count"] == before + 1
    assert created["id"] in [c["id"] for c in body["categories"]]
    assert "Barhi" in [c["name"] for c in body["categories"]]


def test_the_count_grows_by_exactly_one_each_time(alice: ApiUser) -> None:
    """9 -> 10 -> 11, as the specification's worked example describes."""
    start = alice.get("/api/categories").json()["count"]

    alice.post("/api/categories", json={"name": "Barhi"})
    assert alice.get("/api/categories").json()["count"] == start + 1

    alice.post("/api/categories", json={"name": "Deglet Noor"})
    assert alice.get("/api/categories").json()["count"] == start + 2


def test_a_user_category_never_becomes_a_model_class(alice: ApiUser) -> None:
    """Adding a category must not pretend the AI has learned it.

    The model is fixed and is never retrained, so a user-added variety exists in
    the database only. Its ``source`` is what keeps that honest.
    """
    created = alice.post("/api/categories", json={"name": "Barhi"}).json()
    assert created["source"] == "USER"

    model_names = set(load_class_names())
    assert created["name"] not in model_names


# ---------------------------------------------------------------------------
# Normalisation and duplicates
# ---------------------------------------------------------------------------
def test_a_repeated_name_returns_the_existing_row_not_an_error(alice: ApiUser) -> None:
    first = alice.post("/api/categories", json={"name": "Barhi"})
    second = alice.post("/api/categories", json={"name": "Barhi"})

    assert first.status_code == 201, first.text
    assert second.status_code == 200, second.text
    assert second.json()["id"] == first.json()["id"]


def test_capitals_and_spacing_all_resolve_to_one_row(alice: ApiUser) -> None:
    """The four spellings from the specification must be one category, not four."""
    created = alice.post("/api/categories", json={"name": "Barhi"})
    assert created.status_code == 201, created.text
    original_id = created.json()["id"]

    for spelling in ("barhi", "BARHI", "  Barhi  ", "  bArHi"):
        response = alice.post("/api/categories", json={"name": spelling})
        assert response.status_code == 200, f"{spelling!r}: {response.text}"
        assert response.json()["id"] == original_id, f"{spelling!r} made a new row"
        assert response.json()["name"] == "Barhi"


def test_inner_whitespace_is_collapsed(alice: ApiUser) -> None:
    """"nabtat   ali" and "Nabtat Ali" are the same variety.

    This matters for a seeded name in particular: Nabtat Ali already exists as a
    MODEL category, so the collapsed form has to match it rather than create a
    second one.
    """
    response = alice.post("/api/categories", json={"name": "nabtat   ali"})

    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Nabtat Ali"
    assert response.json()["source"] == "MODEL"


def test_a_seeded_name_typed_in_lower_case_finds_the_seeded_row(
    alice: ApiUser, category_ids: dict[str, int]
) -> None:
    response = alice.post("/api/categories", json={"name": "medjool"})

    assert response.status_code == 200, response.text
    assert response.json()["id"] == category_ids["Medjool"]
    assert response.json()["source"] == "MODEL"


def test_adding_a_duplicate_does_not_change_the_total(alice: ApiUser) -> None:
    alice.post("/api/categories", json={"name": "Barhi"})
    after_first = alice.get("/api/categories").json()["count"]

    alice.post("/api/categories", json={"name": "BARHI"})
    assert alice.get("/api/categories").json()["count"] == after_first


def test_a_multi_word_name_is_title_cased(alice: ApiUser) -> None:
    response = alice.post("/api/categories", json={"name": "deglet   noor"})
    assert response.status_code == 201, response.text
    assert response.json()["name"] == "Deglet Noor"


# ---------------------------------------------------------------------------
# Rejecting names that are not names
# ---------------------------------------------------------------------------
def test_a_name_with_no_letters_is_refused(alice: ApiUser) -> None:
    """"123" and "!!!" would clutter everyone's dropdown."""
    for name in ("123", "!!!", "-", "42"):
        response = alice.post("/api/categories", json={"name": name})
        assert response.status_code == 422, f"{name!r} was accepted: {response.text}"


def test_a_blank_name_is_refused(alice: ApiUser) -> None:
    for name in ("", "   ", "\t\n"):
        response = alice.post("/api/categories", json={"name": name})
        assert response.status_code == 422, f"{name!r} was accepted: {response.text}"


def test_an_over_long_name_is_refused(alice: ApiUser) -> None:
    """The column is String(80), so this is a clear 422 rather than a DB error."""
    response = alice.post("/api/categories", json={"name": "B" * 81})
    assert response.status_code == 422, response.text


def test_a_name_of_exactly_the_limit_is_accepted(alice: ApiUser) -> None:
    response = alice.post("/api/categories", json={"name": "B" * 80})
    assert response.status_code == 201, response.text


def test_a_missing_name_field_is_refused(alice: ApiUser) -> None:
    assert alice.post("/api/categories", json={}).status_code == 422


def test_a_name_with_letters_in_another_script_is_accepted(alice: ApiUser) -> None:
    """``.isalpha()`` understands letters in any script, not just English.

    Rejecting a Bengali variety name would make the project unusable for the
    people it is actually for.
    """
    response = alice.post("/api/categories", json={"name": "খেজুর"})
    assert response.status_code == 201, response.text

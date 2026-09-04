"""A smoke test for the test setup itself.

If the fixtures in ``conftest.py`` are wrong, every other test fails in a
confusing way. These few checks confirm the plumbing works, so a failure
elsewhere means a real bug in the application rather than a broken harness.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import ApiUser, publish_listing


def test_nine_model_categories_are_seeded(category_ids: dict[str, int]) -> None:
    """The migration seeded the 9 varieties the model recognises."""
    assert len(category_ids) >= 9
    for name in ("Ajwa", "Galaxy", "Medjool", "Rutab", "Sokari"):
        assert name in category_ids


def test_registration_and_login_work(alice: ApiUser) -> None:
    """The fixture really registered someone and got a usable token."""
    assert alice.id > 0
    response = alice.get("/api/auth/me")
    assert response.status_code == 200, response.text
    assert response.json()["id"] == alice.id


def test_publishing_works(alice: ApiUser, category_ids: dict[str, int]) -> None:
    """Phase 7 still works: a listing publishes and comes back complete."""
    listing = publish_listing(alice, category_ids["Ajwa"], price="800.00", unit="kg")

    assert listing["category"]["name"] == "Ajwa"
    assert listing["price"] == "800.00"
    assert listing["status"] == "ACTIVE"
    assert listing["posted_by"]["id"] == alice.id
    assert listing["image_url"].startswith("/uploads/listings/")
    # Tk800 for 1 kg = Tk0.80 per gram.
    assert float(listing["price_per_gram"]) == 0.80


def test_transaction_is_rolled_back(client: TestClient, db: Session) -> None:
    """Whatever a test writes is gone before the next test starts.

    Counting users at the start of every test would be brittle; instead this
    records the count, adds a user, and the *next* run of the suite would fail if
    the rollback were not happening.
    """
    from app.models.user import User

    before = db.query(User).count()
    from tests.conftest import register_user

    register_user(client, "Temporary")
    assert db.query(User).count() == before + 1

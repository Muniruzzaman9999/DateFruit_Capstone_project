"""Shared test setup: a real database, a real API client, real logged-in users.

How these tests talk to the database
------------------------------------
They use **the real PostgreSQL database**, inside a transaction that is rolled
back when the test finishes. Nothing a test writes survives it, so the tests can
be run over and over on the development machine without filling the marketplace
with "Test Shop" listings.

The mechanism is worth understanding, because it is the part that is easy to get
wrong. For each test:

1. open one connection and begin a transaction on it
2. bind a Session to *that connection*
3. make the API's ``get_db`` dependency hand out that same session
4. when the test ends, roll the transaction back and close the connection

Because the API and the test share one connection, a row the test inserts is
visible to the endpoint under test, and vice versa - while still vanishing at the
end. Committing inside the endpoint is fine: with an outer transaction already
open, SQLAlchemy turns those commits into savepoint releases, and the outer
rollback still discards everything.

Why not a separate test database? It would need its own migrations and its own
seeded categories, and the point of these tests is to check the application
against the schema it actually runs on. A rolled-back transaction gives the same
isolation without a second copy of the schema to keep in step.

Why the model is not loaded
---------------------------
``WARM_MODEL_ON_STARTUP`` is forced to ``false`` before the app is imported.
Loading the real 330 MB Keras model takes several seconds and a few hundred MB of
RAM, and none of these tests classify an image. The tests that do need the model
load it themselves and are marked ``slow``.
"""

from __future__ import annotations

import io
import os
from collections.abc import Iterator
from pathlib import Path

import pytest

# Must happen before app.main is imported, since the lifespan reads it at startup.
os.environ["WARM_MODEL_ON_STARTUP"] = "false"

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import LISTING_IMAGE_DIR  # noqa: E402
from app.db.session import SessionLocal, engine, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.category import DateFruitCategory  # noqa: E402


# ---------------------------------------------------------------------------
# Image files on disk
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def clean_up_image_files() -> Iterator[None]:
    """Delete any listing image a test leaves behind.

    Rolling back the database transaction cannot undo a file write - the photo of
    a listing that no longer exists would sit in ``backend/uploads/listings/``
    forever. So this notes which files were there before the test and removes
    anything new afterwards.

    It is careful to remove only files the test created. Comparing against a
    snapshot, rather than emptying the folder, means running the tests can never
    delete a photo belonging to a listing published by hand while developing.
    """
    LISTING_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    before = set(LISTING_IMAGE_DIR.iterdir())

    yield

    for path in LISTING_IMAGE_DIR.iterdir():
        if path not in before and path.is_file():
            path.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def reset_db_data() -> Iterator[None]:
    """Clean up dynamic test data before each test run."""
    import sqlalchemy as sa  # noqa: E402
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM listings"))
        conn.execute(sa.text("DELETE FROM users"))
        conn.execute(sa.text("DELETE FROM date_fruit_categories WHERE source = 'USER'"))
        if engine.name == "sqlite":
            try:
                conn.execute(sa.text("DELETE FROM sqlite_sequence WHERE name IN ('listings', 'users', 'date_fruit_categories')"))
            except Exception:
                pass
    yield


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
@pytest.fixture
def db() -> Iterator[Session]:
    if engine.name == "sqlite":
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()
    else:
        connection = engine.connect()
        transaction = connection.begin()
        session = SessionLocal(bind=connection, join_transaction_mode="create_savepoint")

        try:
            yield session
        finally:
            session.close()
            transaction.rollback()
            connection.close()


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    """An API client for testing endpoint handlers."""

    def override_get_db() -> Iterator[Session]:
        if engine.name == "sqlite":
            session = SessionLocal()
            try:
                yield session
            finally:
                session.close()
        else:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------
def make_image_bytes(colour: str = "red", size: tuple[int, int] = (40, 40)) -> bytes:
    """A tiny real JPEG, generated in memory.

    Real image bytes rather than ``b"not an image"``, because the upload path
    genuinely decodes the file with Pillow to work out its format. 40x40 pixels
    keeps it small enough that saving hundreds of them costs nothing.
    """
    image = Image.new("RGB", size, colour)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def image_upload(
    filename: str = "photo.jpg", colour: str = "red"
) -> dict[str, tuple[str, bytes, str]]:
    """The ``files=`` argument for a multipart request carrying one image."""
    return {"image": (filename, make_image_bytes(colour), "image/jpeg")}


def image_file_for(listing: dict) -> Path:
    """The file on disk that a listing's ``image_url`` points at.

    ``/uploads/listings/9f2c.jpg``  ->  ``backend/uploads/listings/9f2c.jpg``

    Used to check that replacing a photo really deletes the old file, and that
    deactivating a listing really does not.
    """
    filename = listing["image_url"].rsplit("/", 1)[-1]
    return LISTING_IMAGE_DIR / filename


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
class ApiUser:
    """One registered, logged-in user, plus the header that proves it.

    Wrapping this up means a test reads ``alice.post(...)`` rather than repeating
    the Authorization header on every single call.
    """

    def __init__(self, client: TestClient, user: dict, token: str) -> None:
        self._client = client
        self.id: int = user["id"]
        self.name: str = user["name"]
        self.email: str = user["email"]
        self.token = token
        self.headers = {"Authorization": f"Bearer {token}"}

    def request(self, method: str, url: str, **kwargs):
        headers = {**self.headers, **kwargs.pop("headers", {})}
        return self._client.request(method, url, headers=headers, **kwargs)

    def get(self, url: str, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs):
        return self.request("POST", url, **kwargs)

    def patch(self, url: str, **kwargs):
        return self.request("PATCH", url, **kwargs)


_user_counter = 0


def register_user(client: TestClient, name: str = "Test User") -> ApiUser:
    """Register a brand-new user and log them in.

    The email is made unique with a counter. Registration goes through the real
    endpoint rather than inserting a row directly, so the password really is
    hashed by the application and the login really is exercised.

    ``example.com`` rather than something like ``example.test``: the ``.test``
    top-level domain is reserved, and the email validator behind ``EmailStr``
    rejects it outright.
    """
    global _user_counter
    _user_counter += 1
    email = f"test-user-{_user_counter}@example.com"
    password = "test-password-123"

    response = client.post(
        "/api/auth/register",
        json={
            "name": name,
            "email": email,
            "password": password,
            "contact_number": "01711222333",
        },
    )
    assert response.status_code == 201, response.text
    user = response.json()

    login = client.post("/api/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text

    return ApiUser(client, user, login.json()["access_token"])


@pytest.fixture
def alice(client: TestClient) -> ApiUser:
    """A logged-in user who owns things."""
    return register_user(client, "Alice")


@pytest.fixture
def bob(client: TestClient) -> ApiUser:
    """A second logged-in user, for checking that ownership is enforced."""
    return register_user(client, "Bob")


# ---------------------------------------------------------------------------
# Categories and listings
# ---------------------------------------------------------------------------
@pytest.fixture
def category_ids(db: Session) -> dict[str, int]:
    """The seeded MODEL categories, by name.

    Read from the database rather than hard-coded, so the tests describe what is
    really there. The 9 rows come from the migration, which seeds them from
    ``model/classes.json``.
    """
    rows = db.scalars(select(DateFruitCategory)).all()
    return {row.name: row.id for row in rows}


def publish_listing(
    user: ApiUser,
    category_id: int,
    *,
    price: str = "800.00",
    quantity: str = "1",
    unit: str = "kg",
    shop_name: str = "Test Dates Shop",
    contact_number: str = "01711222333",
    shop_location: str = "Mirpur, Dhaka",
    colour: str = "red",
) -> dict:
    """Publish one listing through the real API and return its JSON."""
    response = user.post(
        "/api/listings",
        data={
            "category_id": category_id,
            "price": price,
            "quantity": quantity,
            "unit": unit,
            "shop_name": shop_name,
            "contact_number": contact_number,
            "shop_location": shop_location,
        },
        files=image_upload(colour=colour),
    )
    assert response.status_code == 201, response.text
    return response.json()

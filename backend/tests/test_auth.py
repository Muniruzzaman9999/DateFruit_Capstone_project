"""PHASE 13 - the specification's authentication test list (section 74).

Covers: registration, duplicate email, login, invalid password, protected
endpoints, the authenticated ``/me`` call, and logout behaviour.

Two ideas here are worth understanding before reading the tests.

**A wrong password and an unknown email must be indistinguishable.** If the API
said "no account with that email", anyone could type addresses in one at a time
to discover who has registered. Several tests below exist purely to pin that
down.

**Logout cannot revoke a JWT.** The token is *stateless*: the server keeps no
list of who is logged in, so it has no way to cancel a token already out in the
world. Logging out really happens in the browser, by deleting the stored token.
That is not a bug, and the test named after it records the real behaviour rather
than pretending otherwise.
"""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User
from tests.conftest import ApiUser

GOOD_PASSWORD = "a-good-password"


def register(client: TestClient, **overrides) -> httpx.Response:
    """POST /api/auth/register with sensible defaults, overridable per test."""
    payload = {
        "name": "Rahim Uddin",
        "email": "rahim@example.com",
        "password": GOOD_PASSWORD,
        "contact_number": "01711222333",
    }
    payload.update(overrides)
    return client.post("/api/auth/register", json=payload)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
def test_registration_returns_the_new_account(client: TestClient) -> None:
    response = register(client)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Rahim Uddin"
    assert body["email"] == "rahim@example.com"
    assert body["contact_number"] == "01711222333"
    assert body["id"] > 0
    assert "created_at" in body


def test_registration_never_reveals_the_password(client: TestClient) -> None:
    """Neither the password nor its hash may appear in any response.

    ``UserResponse`` lists the fields the API is allowed to return, and the hash
    is not among them - so even though the database row carries it, it cannot
    leak by accident. This test is what stops someone adding it later.
    """
    body = register(client).json()

    assert "password" not in body
    assert "password_hash" not in body
    # Searched across the whole flattened response, not just the top-level keys,
    # in case it ever appears nested inside something.
    assert GOOD_PASSWORD not in repr(body)


def test_the_password_is_hashed_in_the_database(client: TestClient, db: Session) -> None:
    """What is stored must not be the password itself."""
    register(client)

    user = db.scalars(select(User).where(User.email == "rahim@example.com")).one()
    assert user.password_hash != GOOD_PASSWORD
    # bcrypt hashes start with $2b$ and are 60 characters long.
    assert user.password_hash.startswith("$2")
    assert len(user.password_hash) >= 55


def test_a_duplicate_email_is_refused(client: TestClient) -> None:
    register(client)
    second = register(client, name="Someone Else")

    assert second.status_code == 409, second.text
    assert "already registered" in second.json()["detail"].lower()


def test_a_duplicate_email_is_refused_whatever_the_capitals(client: TestClient) -> None:
    """"Rahim@Example.com" is the same mailbox as "rahim@example.com".

    Without normalisation the UNIQUE index would not stop the second sign-up,
    and one person would end up with two accounts.
    """
    register(client, email="rahim@example.com")
    second = register(client, email="Rahim@EXAMPLE.com")

    assert second.status_code == 409, second.text


def test_the_email_is_stored_lower_cased(client: TestClient) -> None:
    body = register(client, email="  RAHIM@Example.Com  ").json()
    assert body["email"] == "rahim@example.com"


def test_a_short_password_is_refused(client: TestClient) -> None:
    response = register(client, password="short")
    assert response.status_code == 422, response.text


def test_a_password_too_long_for_bcrypt_is_refused(client: TestClient) -> None:
    """bcrypt cannot hash more than 72 bytes, so this is caught politely.

    Bytes, not characters: an emoji costs several bytes each, so this 40-emoji
    password is well over the limit despite being only 40 characters.
    """
    response = register(client, password="🌴" * 40)
    assert response.status_code == 422, response.text
    assert "too long" in response.text.lower()


def test_a_name_of_only_spaces_is_refused(client: TestClient) -> None:
    """``min_length=1`` alone would accept three spaces as a name."""
    response = register(client, name="   ")
    assert response.status_code == 422, response.text


def test_an_invalid_email_is_refused(client: TestClient) -> None:
    response = register(client, email="not-an-email")
    assert response.status_code == 422, response.text


def test_a_contact_number_with_too_few_digits_is_refused(client: TestClient) -> None:
    response = register(client, contact_number="12345")
    assert response.status_code == 422, response.text


def test_a_contact_number_with_letters_is_refused(client: TestClient) -> None:
    response = register(client, contact_number="0171122233x")
    assert response.status_code == 422, response.text


def test_the_ways_people_really_write_phone_numbers_are_accepted(
    client: TestClient,
) -> None:
    for index, number in enumerate(
        ("01711 222333", "+880 1711-222333", "(017) 11222333")
    ):
        response = register(
            client, email=f"person{index}@example.com", contact_number=number
        )
        assert response.status_code == 201, f"{number}: {response.text}"


def test_registration_does_not_ask_for_a_role(client: TestClient) -> None:
    """There are no roles at all, so a sent role must be ignored.

    Pydantic ignores fields it does not declare, so this succeeds and the extra
    value simply goes nowhere. The test exists to prove no role ever comes back.
    """
    response = register(client, role="ADMIN")

    assert response.status_code == 201, response.text
    assert "role" not in response.json()


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
def test_login_returns_a_usable_token(client: TestClient) -> None:
    register(client)
    response = client.post(
        "/api/auth/login", json={"email": "rahim@example.com", "password": GOOD_PASSWORD}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body["access_token"], str) and body["access_token"]
    assert body["token_type"] == "bearer"
    assert isinstance(body["expires_in_minutes"], int)
    assert body["user"]["email"] == "rahim@example.com"
    assert "password_hash" not in body["user"]


def test_login_works_whatever_the_capitals(client: TestClient) -> None:
    register(client, email="rahim@example.com")
    response = client.post(
        "/api/auth/login", json={"email": "RAHIM@Example.com", "password": GOOD_PASSWORD}
    )
    assert response.status_code == 200, response.text


def test_login_with_the_wrong_password_is_401(client: TestClient) -> None:
    register(client)
    response = client.post(
        "/api/auth/login", json={"email": "rahim@example.com", "password": "wrong"}
    )
    assert response.status_code == 401, response.text


def test_login_with_an_unknown_email_is_401(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": GOOD_PASSWORD}
    )
    assert response.status_code == 401, response.text


def test_both_login_failures_give_the_identical_message(client: TestClient) -> None:
    """The reply must not reveal whether the email exists.

    A different message for "no such account" would let anyone test addresses
    one at a time to find out who has registered here.
    """
    register(client)

    wrong_password = client.post(
        "/api/auth/login", json={"email": "rahim@example.com", "password": "wrong"}
    )
    unknown_email = client.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": GOOD_PASSWORD}
    )

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json()["detail"] == unknown_email.json()["detail"]


def test_a_login_failure_detail_is_a_plain_string(client: TestClient) -> None:
    """The React form shows this directly, so it must not be a list."""
    response = client.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": "x"}
    )
    assert isinstance(response.json()["detail"], str)


# ---------------------------------------------------------------------------
# Protected endpoints
# ---------------------------------------------------------------------------
def test_me_returns_the_callers_own_account(alice: ApiUser) -> None:
    response = alice.get("/api/auth/me")

    assert response.status_code == 200, response.text
    assert response.json()["id"] == alice.id
    assert response.json()["email"] == alice.email


def test_me_without_a_token_is_401(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401


def test_me_with_a_nonsense_token_is_401(client: TestClient) -> None:
    response = client.get(
        "/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == 401


def test_me_with_a_token_signed_by_someone_else_is_401(client: TestClient) -> None:
    """A token signed with the wrong secret must not be accepted.

    This is the whole point of signing: without the check, anyone could write
    their own token claiming to be user 1.
    """
    import jwt

    forged = jwt.encode({"sub": "1"}, "not-the-real-secret", algorithm="HS256")
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


def test_two_users_see_their_own_account_and_not_each_others(
    alice: ApiUser, bob: ApiUser
) -> None:
    assert alice.get("/api/auth/me").json()["id"] == alice.id
    assert bob.get("/api/auth/me").json()["id"] == bob.id
    assert alice.id != bob.id


def test_every_protected_endpoint_refuses_an_anonymous_caller(
    client: TestClient,
) -> None:
    """One list, so a new endpoint added without a login check gets noticed."""
    for method, url in (
        ("GET", "/api/auth/me"),
        ("POST", "/api/auth/logout"),
        ("GET", "/api/categories"),
        ("POST", "/api/categories"),
        ("GET", "/api/categories/statistics"),
        ("GET", "/api/categories/1/stats"),
        ("GET", "/api/listings/mine"),
        ("GET", "/api/listings/1"),
        ("POST", "/api/listings"),
        ("PATCH", "/api/listings/1"),
        ("POST", "/api/listings/1/deactivate"),
        ("POST", "/api/listings/1/reactivate"),
        ("GET", "/api/marketplace/listings"),
        ("GET", "/api/marketplace/best-price"),
        ("POST", "/api/ml/predict"),
    ):
        response = client.request(method, url)
        assert response.status_code == 401, f"{method} {url} gave {response.status_code}"


def test_health_and_docs_stay_open(client: TestClient) -> None:
    """These two must NOT need a login - they are how you diagnose the server."""
    assert client.get("/api/health").status_code == 200
    assert client.get("/").status_code == 200
    assert client.get("/docs").status_code == 200


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------
def test_logout_confirms_and_requires_a_login(alice: ApiUser) -> None:
    response = alice.post("/api/auth/logout")

    assert response.status_code == 200, response.text
    assert alice.name in response.json()["message"]


def test_logout_does_not_revoke_the_token(alice: ApiUser) -> None:
    """Recording the real behaviour of a stateless JWT.

    After logging out the token still works, because the server keeps no list of
    cancelled tokens - it cannot know this one was "logged out". The session
    really ends when the browser deletes it, which is what the React app does.

    If token revocation is ever added, this test will fail, and that failure is
    the correct signal to update it.
    """
    assert alice.post("/api/auth/logout").status_code == 200
    assert alice.get("/api/auth/me").status_code == 200

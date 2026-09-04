"""Password hashing and JWT access tokens.

Two separate jobs live in this file.

**Password hashing.** The password itself is never stored. What is stored is a
bcrypt *hash* - a one-way scramble. Logging in re-scrambles whatever was typed
and compares the two scrambles. Even someone who steals the whole database
cannot read anyone's password. bcrypt is deliberately slow (roughly 100 ms
here), which is what makes guessing millions of passwords impractical.

**JWT (JSON Web Token).** After a successful login the server hands the browser
a signed note that says "this is user 7, valid until 14:32". The browser sends
that note back with every later request. The signature is made with
``JWT_SECRET``, so nobody can edit the note - change one character and the
signature stops matching. The server therefore does not need to remember who is
logged in; the note carries its own proof. That is also why the secret must be
long, random, and different on every machine.

What is deliberately NOT in the token
-------------------------------------
Only the user's id. This application has no roles, and nothing else about the
account is copied into the token. That matters: a token is issued once and then
lives for an hour, so anything baked into it can go stale. The id never changes,
and everything else (name, contact number) is read fresh from the database on
each request.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings

# bcrypt hashes at most 72 bytes of a password. Older versions silently ignored
# anything beyond that; bcrypt 5 raises instead. Requests are rejected before
# they reach here (see app/schemas/auth.py), so the user gets a clear message
# rather than a 500.
BCRYPT_MAX_PASSWORD_BYTES = 72


class InvalidTokenError(Exception):
    """The token is missing, malformed, expired, or has a bad signature."""


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    """Turn a plain password into a bcrypt hash, ready to store."""
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > BCRYPT_MAX_PASSWORD_BYTES:
        raise ValueError(
            f"Password is too long for bcrypt: {len(password_bytes)} bytes, "
            f"maximum {BCRYPT_MAX_PASSWORD_BYTES}."
        )
    # gensalt() produces a fresh random salt every time, so two people who
    # happen to choose the same password still end up with different hashes.
    # Without that, identical hashes would reveal identical passwords.
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Check a typed password against a stored hash. Never raises."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        # A malformed or truncated hash in the database must mean "login
        # failed", not "server error".
        return False


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------
def create_access_token(user_id: int) -> str:
    """Build a signed token identifying this user."""
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        # "sub" (subject) is the standard JWT field for "who this is about".
        # The JWT specification requires it to be a string, hence str().
        "sub": str(user_id),
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> int:
    """Verify a token and return the user id inside it.

    Raises ``InvalidTokenError`` for every kind of failure - expired, tampered
    with, signed by a different secret, or simply not a token at all. The caller
    turns that into one consistent 401.

    ``options={"require": [...]}`` makes PyJWT insist both claims are present.
    Without it, a token with no ``exp`` would be treated as valid forever.
    """
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise InvalidTokenError(
            "Your session has expired. Please log in again."
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError("Invalid authentication token.") from exc

    try:
        return int(claims["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidTokenError("Invalid authentication token.") from exc

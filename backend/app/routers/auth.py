"""Authentication endpoints.

    POST /api/auth/register   create an account
    POST /api/auth/login      exchange email + password for a token
    GET  /api/auth/me          who am I?
    POST /api/auth/logout      confirm a logout
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter(prefix="/api/auth", tags=["authentication"])

# A throwaway hash, computed once when this module is imported. See login() for
# why it has to exist.
_TIMING_DECOY_HASH = hash_password("this-hash-never-belongs-to-a-real-account")

_EMAIL_TAKEN = "That email address is already registered."


def _commit_or_conflict(db: Session) -> None:
    """Commit, turning a duplicate-email crash into a clean 409.

    The email is checked before this is called, but two people could register
    the same address in the same instant and both pass that check. The UNIQUE
    index in PostgreSQL is the real guarantee; this converts its raw error into
    a message a person can act on.
    """
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if "ix_users_email" in str(exc.orig):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=_EMAIL_TAKEN
            ) from exc
        raise


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account",
)
def register(payload: RegisterRequest, db: DbSession) -> User:
    """Register a new user.

    Everyone who registers gets the same kind of account: they can classify
    images, publish listings, browse everyone else's, and edit their own.

    The password is hashed before it is stored and is never written to the
    database, the logs, or any response.
    """
    existing = db.scalars(select(User.id).where(User.email == payload.email)).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=_EMAIL_TAKEN
        )

    user = User(
        name=payload.name,
        email=payload.email,  # already lower-cased by the schema
        password_hash=hash_password(payload.password),
        contact_number=payload.contact_number,
    )
    db.add(user)
    _commit_or_conflict(db)
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse, summary="Log in and get a token")
def login(payload: LoginRequest, db: DbSession) -> TokenResponse:
    """Exchange an email and password for a signed access token.

    Both "no such email" and "wrong password" return exactly the same message,
    on purpose. A reply like "no account with that email" would let anyone test
    addresses one by one to discover who has registered here.
    """
    user = db.scalars(select(User).where(User.email == payload.email)).first()

    if user is None:
        # Hash against a decoy so a missing account takes about as long as a
        # wrong password does. Without this the *response time* would reveal
        # whether the email exists, which defeats the identical message above.
        verify_password(payload.password, _TIMING_DECOY_HASH)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )

    return TokenResponse(
        access_token=create_access_token(user_id=user.id),
        expires_in_minutes=settings.jwt_expire_minutes,
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse, summary="View your own account")
def read_current_user(user: CurrentUser) -> User:
    """Return the account belonging to the token that was sent.

    The React app calls this on page load: it has a token in storage but does
    not know whether it is still valid, and this is the cheapest way to find out.
    """
    return user


@router.post("/logout", response_model=MessageResponse, summary="Log out")
def logout(user: CurrentUser) -> MessageResponse:
    """Confirm a logout.

    Worth understanding, because it surprises people: a JWT is *stateless*. The
    server keeps no list of who is logged in, so it cannot cancel a token that
    is already out in the world - that token stays valid until it expires
    (JWT_EXPIRE_MINUTES, 60 by default).

    Logging out therefore really happens in the browser, by deleting the stored
    token, which is exactly what the React app does. This endpoint exists so the
    app has something to call and so the behaviour is documented rather than
    quietly assumed.

    Truly revoking a token early would need the server to keep a blocklist of
    cancelled tokens. That is deliberately out of scope, and is written up as a
    known limitation in the README.
    """
    return MessageResponse(
        message=f"Goodbye {user.name}. Delete the token in your browser to "
        "finish logging out."
    )

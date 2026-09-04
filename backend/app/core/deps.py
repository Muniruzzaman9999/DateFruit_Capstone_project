"""Shared FastAPI dependencies: the database session, and "who is calling?".

A *dependency* in FastAPI is a function you attach to an endpoint. FastAPI runs
it before the endpoint and hands the result in as an argument. Putting the token
check in one dependency means every protected endpoint gets identical, correct
behaviour, instead of each one re-implementing it slightly differently and one
of them getting it wrong.

Note what is NOT here: any notion of a role or an account type. This application
has one kind of user. The only permission question it ever asks is "do you own
this listing?", and that is answered in ``app/routers/listings.py``, where the
listing is actually loaded.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import InvalidTokenError, decode_access_token
from app.db.session import get_db
from app.models.user import User

#: One database session per request. Used as ``db: DbSession`` in an endpoint.
DbSession = Annotated[Session, Depends(get_db)]

# Reads the "Authorization: Bearer <token>" header.
#
# auto_error=False means FastAPI hands us ``None`` for a missing header instead
# of raising its own terser error, so every failure below produces the same
# message shape. This is also what puts the "Authorize" button on the Swagger
# docs page at /docs.
bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Paste the access_token returned by POST /api/auth/login",
)


def _unauthorized(detail: str) -> HTTPException:
    """401 with the header the HTTP standard asks for on a failed auth."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
    db: DbSession,
) -> User:
    """Turn the token in the request header into a real database row.

    Everything that can go wrong ends in a 401: no header, a garbage token, an
    expired token, a token signed with a different secret, or a token for an
    account that has since been deleted.

    The last case matters more than it looks. A token stays valid until it
    expires, so a deleted account could otherwise keep making requests for up to
    an hour. Looking the user up on every request closes that window.
    """
    if credentials is None or not credentials.credentials:
        raise _unauthorized(
            "Not authenticated. Send an 'Authorization: Bearer <token>' header."
        )

    try:
        user_id = decode_access_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise _unauthorized(str(exc)) from exc

    user = db.get(User, user_id)
    if user is None:
        raise _unauthorized("The account for this token no longer exists.")

    return user


#: Used as ``user: CurrentUser`` in an endpoint that requires a login.
CurrentUser = Annotated[User, Depends(get_current_user)]

"""Request and response shapes for registration, login and the current account.

A *schema* is the contract for one message. FastAPI uses these to validate what
arrives, to decide what goes out, and to write the /docs page automatically.

The most important one here is :class:`UserResponse`, which lists the fields the
API is allowed to reveal about an account. ``password_hash`` is not among them,
so it cannot leak by accident even though the ``User`` database row carries it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
)

from app.core.security import BCRYPT_MAX_PASSWORD_BYTES
from app.schemas.common import ContactNumber

#: Shortest password the API accepts. Long enough to be worth hashing, short
#: enough not to annoy someone registering for a university project.
MIN_PASSWORD_LENGTH = 8


def _normalise_email(value: str) -> str:
    """Store and compare every email in one consistent form.

    "Rahim@Example.com" and "rahim@example.com" are the same mailbox, so without
    this a person could register twice and the UNIQUE index would not stop them.
    Because it lives on the shared type below, registration *and* login both get
    it - forgetting it in one place is the classic version of this bug.
    """
    return value.strip().lower()


#: An email address, validated then lower-cased.
NormalisedEmail = Annotated[EmailStr, AfterValidator(_normalise_email)]


class RegisterRequest(BaseModel):
    """Creating an account.

    Four fields, exactly as the specification asks. There is deliberately no
    role, account type, or "are you a shop owner?" question: everyone who
    registers gets the same account and the same abilities.
    """

    name: str = Field(
        min_length=1, max_length=120, description="Your full name.",
        examples=["Rahim Uddin"],
    )
    email: NormalisedEmail = Field(
        description="Used to log in. Stored lower-case.",
        examples=["rahim@example.com"],
    )
    password: str = Field(
        min_length=MIN_PASSWORD_LENGTH,
        description=f"At least {MIN_PASSWORD_LENGTH} characters.",
        examples=["a-good-password"],
    )
    contact_number: ContactNumber

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        """Reject a name that is only spaces, which min_length alone allows."""
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Please enter your name.")
        return cleaned

    @field_validator("password")
    @classmethod
    def _check_password_fits_bcrypt(cls, value: str) -> str:
        """bcrypt cannot hash more than 72 bytes, so refuse politely here.

        Bytes, not characters: an emoji or an accented letter costs several
        bytes, so a 40-character password can still be over the limit. Catching
        it in the schema turns a 500 into a clear message.
        """
        length = len(value.encode("utf-8"))
        if length > BCRYPT_MAX_PASSWORD_BYTES:
            raise ValueError(
                f"Password is too long ({length} bytes). The maximum is "
                f"{BCRYPT_MAX_PASSWORD_BYTES} bytes. Note that accented letters "
                "and emoji count as more than one byte each."
            )
        return value


class LoginRequest(BaseModel):
    """Logging in. No length rules here on purpose.

    Validating the password's shape at login would be pointless - and worse, a
    "password too short" reply would tell an attacker their guess was rejected
    for the wrong reason. Every failure gets the same answer instead.
    """

    email: NormalisedEmail
    password: str


class UserResponse(BaseModel):
    """An account, as the API is allowed to describe it.

    ``password_hash`` is absent by design. Pydantic copies only the fields
    declared here, so even though the database row carries the hash it can never
    reach a response.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
    contact_number: str
    created_at: datetime


class TokenResponse(BaseModel):
    """What a successful login returns."""

    access_token: str = Field(
        description="Send this back as 'Authorization: Bearer <token>'."
    )
    token_type: str = Field(
        default="bearer", description="Always 'bearer' for this API."
    )
    expires_in_minutes: int = Field(
        description="How long the token stays valid, from now."
    )
    user: UserResponse


class MessageResponse(BaseModel):
    """A plain confirmation, used by logout."""

    message: str

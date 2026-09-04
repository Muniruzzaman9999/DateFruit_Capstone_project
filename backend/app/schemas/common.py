"""Field types shared by more than one schema.

A contact number is collected in two different places - once at registration for
the account holder, and again on every listing for that shop's phone line. The
validation rules are identical, so they are defined here once. Two copies of a
rule like this is how the two quietly drift apart.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator, Field

#: A contact number must contain at least this many digits to be plausible.
MIN_CONTACT_DIGITS = 7

#: The only non-digit characters a phone number may contain.
_ALLOWED_NUMBER_CHARACTERS = "0123456789 +-()"


def _validate_contact_number(value: str) -> str:
    """Accept the ways people really write phone numbers; reject nonsense.

    "01711 222333", "+880 1711-222333" and "(017) 11222333" are all fine. The
    check counts *digits* rather than matching one country's format, because
    hard-coding a Bangladeshi pattern would make the project fail for anyone
    else - and portability is a requirement here.
    """
    cleaned = " ".join(value.split())
    digits = sum(character.isdigit() for character in cleaned)

    if digits < MIN_CONTACT_DIGITS:
        raise ValueError(
            f"That does not look like a phone number - it contains only "
            f"{digits} digit(s). Please enter at least {MIN_CONTACT_DIGITS}, "
            "for example 01711222333."
        )
    if any(character not in _ALLOWED_NUMBER_CHARACTERS for character in cleaned):
        raise ValueError(
            "A contact number may contain only digits, spaces, and the "
            "characters + - ( )."
        )
    return cleaned


#: A phone number, with surrounding and repeated whitespace tidied up.
ContactNumber = Annotated[
    str,
    Field(
        min_length=MIN_CONTACT_DIGITS,
        max_length=30,
        description="Digits, optionally with spaces, +, -, or brackets.",
        examples=["01711222333"],
    ),
    AfterValidator(_validate_contact_number),
]

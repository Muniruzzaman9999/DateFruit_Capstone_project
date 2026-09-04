"""Request and response shapes for date-fruit categories."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.category import CategorySource, canonical_category_name

#: Matches the String(80) column. Enforced here so an over-long name is a clear
#: 422 rather than a database error.
MAX_CATEGORY_NAME_LENGTH = 80


class CategoryCreateRequest(BaseModel):
    """Adding a new date-fruit category (the "Other / New Category" flow).

    The name is cleaned up and checked here, before it reaches the database, so
    the person gets a useful message instead of a constraint violation.
    """

    name: str = Field(
        min_length=1,
        max_length=MAX_CATEGORY_NAME_LENGTH,
        description=(
            "The variety name. Case and extra spaces do not matter: 'barhi', "
            "'BARHI' and ' Barhi ' are all stored as 'Barhi'."
        ),
        examples=["Barhi"],
    )

    @field_validator("name")
    @classmethod
    def _clean_and_check(cls, value: str) -> str:
        """Normalise the name, then reject anything that is not a plausible one.

        Normalising *here* means the value the endpoint receives is already the
        exact string that will be stored, so there is no gap between what was
        validated and what gets written.
        """
        name = canonical_category_name(value)

        if not name:
            raise ValueError("Please enter a category name.")
        if len(name) > MAX_CATEGORY_NAME_LENGTH:
            raise ValueError(
                f"That name is too long ({len(name)} characters). The maximum is "
                f"{MAX_CATEGORY_NAME_LENGTH}."
            )
        # A variety name has to contain a letter. Without this check, "123" or
        # "!!!" would become categories and clutter everyone's dropdown.
        # `.isalpha()` understands letters in any script, not just English.
        if not any(character.isalpha() for character in name):
            raise ValueError(
                "A category name must contain at least one letter - for example "
                "'Barhi' or 'Deglet Noor'."
            )
        return name


class CategoryResponse(BaseModel):
    """One category, as the API reports it."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str = Field(examples=["Medjool"])
    source: CategorySource = Field(
        description=(
            "MODEL means the AI can recognise this variety. USER means somebody "
            "added it, so it can be chosen manually but will never be predicted."
        )
    )
    created_at: datetime


class CategoryListResponse(BaseModel):
    """Everything needed to fill a category dropdown."""

    count: int = Field(description="How many categories exist in total.")
    categories: list[CategoryResponse]

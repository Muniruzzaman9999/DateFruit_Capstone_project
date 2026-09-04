"""Database models.

Importing every model class here matters for two reasons:

1. SQLAlchemy can only resolve the relationships between the tables once all of
   the classes have been imported. ``Listing`` refers to ``User`` and
   ``DateFruitCategory`` by name, and those names are looked up at this point.
2. Alembic compares ``Base.metadata`` against the real database to work out what
   a migration should contain. A model that was never imported is invisible to
   Alembic and would be silently left out.

The three tables:

    users                    one account per person; no roles
    date_fruit_categories    the 9 model varieties, plus any users add
    listings                 one priced offer, owned by one user
"""

from app.db.base import Base
from app.models.category import (
    CategorySource,
    DateFruitCategory,
    canonical_category_name,
)
from app.models.listing import (
    GRAM_BASED_UNITS,
    GRAMS_PER_KG,
    Listing,
    ListingStatus,
    ListingUnit,
)
from app.models.user import User

__all__ = [
    "Base",
    "CategorySource",
    "DateFruitCategory",
    "GRAMS_PER_KG",
    "GRAM_BASED_UNITS",
    "Listing",
    "ListingStatus",
    "ListingUnit",
    "User",
    "canonical_category_name",
]

"""The shape of the ``GET /api/health`` response."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    """Whether the two things the application depends on are usable.

    ``protected_namespaces=()`` is needed only because Pydantic reserves names
    beginning with ``model_`` for its own use and would otherwise print a
    warning about ``model_loaded``. The field name is fixed by the API contract,
    so the reservation is switched off for this one schema rather than renaming
    the field.
    """

    model_config = ConfigDict(protected_namespaces=())

    status: str = Field(
        description='"healthy" when everything works, otherwise "degraded".',
        examples=["healthy"],
    )
    model_loaded: bool = Field(
        description="True once the Keras model is in memory and ready to predict."
    )
    database_connected: bool = Field(
        description="True when a test query against PostgreSQL succeeded."
    )

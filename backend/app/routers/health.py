"""The health-check endpoint.

    GET /api/health
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.health import HealthResponse
from app.services.ml_service import classifier

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health", response_model=HealthResponse, summary="Service health")
def health(db: Annotated[Session, Depends(get_db)]) -> HealthResponse:
    """Report whether PostgreSQL and the model are both usable.

    Two deliberate choices here.

    **No login required.** This is the endpoint you check when something is
    broken. Needing a working login to ask "is the database up?" would defeat
    the purpose.

    **Always answers 200**, with the trouble described in the ``status`` field
    rather than as an error code. That way you can always read *which* half is
    unhealthy instead of getting a bare 500.
    """
    database_connected = False
    try:
        # The cheapest query that proves a live connection.
        db.execute(text("SELECT 1"))
        database_connected = True
    except Exception as exc:  # noqa: BLE001 - any failure here means "not connected"
        logger.warning("Health check: database unreachable: %s", exc)

    model_loaded = classifier.is_loaded

    return HealthResponse(
        status="healthy" if (database_connected and model_loaded) else "degraded",
        model_loaded=model_loaded,
        database_connected=database_connected,
    )

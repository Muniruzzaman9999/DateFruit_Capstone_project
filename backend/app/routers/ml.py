"""The image classification endpoint.

    POST /api/ml/predict     multipart/form-data, field name "file"

The uploaded image is held in memory for the length of the request and is never
written to disk here. A copy is saved only if the person goes on to publish a
listing, which is a separate request handled in ``app/routers/listings.py``.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from app.core.deps import CurrentUser
from app.core.uploads import read_image_upload
from app.schemas.ml import PredictionResponse
from app.services.ml_service import InvalidImageError, ModelLoadError, classifier

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ml", tags=["machine learning"])


@router.post(
    "/predict",
    response_model=PredictionResponse,
    summary="Classify a date-fruit photo",
)
async def predict(
    user: CurrentUser,
    file: UploadFile = File(..., description="A JPG, JPEG, PNG or WEBP image."),
) -> PredictionResponse:
    """Identify the date variety in an uploaded photo.

    Requires a logged-in account. Classifying costs real CPU time and a few
    hundred megabytes of memory, so it is not left open to anonymous callers.

    The upload is validated first - type, then size - by the shared checker in
    ``app/core/uploads.py``, which is the same one the listing endpoint uses so
    the two can never disagree about what counts as an acceptable image.
    """
    data = await read_image_upload(file)

    # --- Classify ----------------------------------------------------------
    # run_in_threadpool moves the blocking TensorFlow work off the event loop.
    # Without it, one slow prediction would freeze every other request in the
    # whole application until it finished.
    try:
        result = await run_in_threadpool(classifier.predict, data, file.filename or "")
    except InvalidImageError as exc:
        # The bytes are not a usable image: corrupt, truncated, or far too many
        # pixels. The person can fix this, so it is a 400.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except ModelLoadError as exc:
        # The server is at fault, not the request, so 503 rather than 4xx.
        logger.error("Model unavailable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "The classification model could not be loaded. Check the server "
                "logs and GET /api/health."
            ),
        ) from exc

    return PredictionResponse(**result)

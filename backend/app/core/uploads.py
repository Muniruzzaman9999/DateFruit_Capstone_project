"""Checking an uploaded image file, before anything expensive happens to it.

Two endpoints receive an image: ``POST /api/ml/predict`` classifies one, and
``POST /api/listings`` saves one alongside a new listing. Both need exactly the
same checks, so they live here once. Two copies of an upload limit is how one of
them quietly ends up with a different limit.

The checks run cheapest-first on purpose. The filename and the declared type are
inspected before any bytes are read; the size limit is enforced before the image
is decoded; only then is it handed to Pillow or TensorFlow. Each step throws away
bad input before it can cost memory or CPU.

These functions raise ``HTTPException`` directly, which is why this module sits in
``core/`` next to the other web-layer helpers rather than in ``services/``. A
service should not know what an HTTP status code is; a request validator is web
plumbing by definition.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings

#: The formats the specification asks for.
ALLOWED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})

#: ``image/jpg`` is not an officially registered type, but plenty of clients send
#: it anyway, so it is accepted.
ALLOWED_CONTENT_TYPES = frozenset(
    {"image/jpeg", "image/jpg", "image/png", "image/webp"}
)


async def read_image_upload(file: UploadFile) -> bytes:
    """Validate one uploaded image and return its bytes.

    Raises ``HTTPException`` with the appropriate status code if the upload is
    missing, of an unsupported type, empty, or over the size limit:

        400  no file, or the file is empty
        415  not a JPG / JPEG / PNG / WEBP
        413  larger than MAX_UPLOAD_BYTES

    Returning the bytes rather than the ``UploadFile`` matters: the caller gets
    something it can both decode *and* write to disk, without having to rewind
    the stream and read it a second time.

    Note this proves only that the upload *claims* to be an image of a supported
    type. Whether the bytes really decode is settled later, by Pillow.
    """
    filename = file.filename or ""
    suffix = Path(filename).suffix.lower()

    # --- 1. Is there a file at all? ----------------------------------------
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file was uploaded. Send a form field named 'file'.",
        )

    # --- 2. Does it claim to be a supported image? -------------------------
    # Accept if EITHER the extension or the declared content type is one we
    # support. Browsers and tools disagree about content types often enough that
    # demanding both agree would reject perfectly good uploads.
    content_type = (file.content_type or "").lower().split(";")[0].strip()
    if suffix not in ALLOWED_EXTENSIONS and content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported file type '{suffix or content_type or 'unknown'}'. "
                "Please upload a JPG, JPEG, PNG or WEBP image."
            ),
        )

    # --- 3. Is it small enough? --------------------------------------------
    # Read one byte MORE than the limit: if that extra byte arrives, the file is
    # too big. This avoids pulling a huge upload fully into memory just to
    # measure it.
    limit = settings.max_upload_bytes
    data = await file.read(limit + 1)
    await file.close()

    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is empty.",
        )
    if len(data) > limit:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=(
                f"That image is larger than the {limit // (1024 * 1024)} MB "
                "limit. Please use a smaller photo."
            ),
        )

    return data

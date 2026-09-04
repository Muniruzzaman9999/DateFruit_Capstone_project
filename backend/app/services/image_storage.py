"""Saving and removing published listing images on disk.

Which images end up here
------------------------
Only images belonging to a **published listing**. An image that was merely
classified and then abandoned is never written to disk - it lives in memory for
the length of the request and is discarded.

Why the file is not stored in PostgreSQL
----------------------------------------
Databases are poor at holding large binary blobs: every backup, every query plan
and every bit of replication traffic has to carry them. The file goes on disk and
the database stores only a short relative path, which is the ordinary way to do
this.

Three rules this module enforces
--------------------------------
**The original filename is never used.** A name arriving from a browser can be
``../../app/main.py``, or 300 characters long, or identical to somebody else's.
Every stored file gets a fresh random name instead.

**The extension comes from the file's real content**, as identified by Pillow -
not from whatever the client called it. A ``.png`` that is really a JPEG gets
stored as ``.jpg``.

**The stored path is relative, with forward slashes**:
``uploads/listings/2b91d4c8....jpg``. Never ``C:\\Users\\...``, so the database
rows stay correct after the project is cloned onto another computer, and never a
Windows backslash, so the same value works as a URL.
"""

from __future__ import annotations

import io
import logging
import secrets
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.core.config import BACKEND_DIR, LISTING_IMAGE_DIR, LISTING_IMAGE_URL_PREFIX

logger = logging.getLogger(__name__)

#: Pillow's format name -> the extension we store it under. Only these three
#: formats are accepted; the four allowed *extensions* collapse into them, since
#: .jpg and .jpeg are both JPEG.
FORMAT_EXTENSIONS: dict[str, str] = {
    "JPEG": ".jpg",
    "PNG": ".png",
    "WEBP": ".webp",
}

#: The path prefix stored in ``listings.image_path``, relative to ``backend/``.
STORED_PATH_PREFIX = "uploads/listings"

#: How many random bytes make up a filename. 16 bytes = 32 hex characters, which
#: is far too large a space for anyone to guess or accidentally collide with.
_FILENAME_BYTES = 16


class UnreadableImageError(ValueError):
    """The bytes are not an image Pillow can decode, so nothing was saved."""


def _detect_extension(image_bytes: bytes) -> str:
    """Confirm the bytes really are a supported image, and return its extension.

    Pillow reads only the file header here, so this is cheap - it does not decode
    the pixels. That is deliberate: the point is to identify the format before
    committing anything to disk.
    """
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            image_format = (image.format or "").upper()
    except UnidentifiedImageError as exc:
        raise UnreadableImageError(
            "That file is not an image we can read. Supported formats: JPG, "
            "JPEG, PNG, WEBP."
        ) from exc
    except OSError as exc:
        raise UnreadableImageError(
            f"The image file appears to be damaged: {exc}"
        ) from exc

    extension = FORMAT_EXTENSIONS.get(image_format)
    if extension is None:
        raise UnreadableImageError(
            f"{image_format or 'That format'} images are not supported. Please "
            "upload a JPG, JPEG, PNG or WEBP image."
        )
    return extension


def save_listing_image(image_bytes: bytes) -> str:
    """Write a published listing's image to disk and return its relative path.

    The return value is exactly what belongs in ``listings.image_path``, for
    example ``uploads/listings/9f2c....jpg``.

    Raises :class:`UnreadableImageError` if the bytes are not a usable image, in
    which case nothing is written.
    """
    if not image_bytes:
        raise UnreadableImageError("The uploaded file is empty.")

    extension = _detect_extension(image_bytes)

    # The folder normally exists already (the application creates it at startup),
    # but a fresh clone may not have it, since Git cannot store an empty folder.
    LISTING_IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    # "xb" means "create a new file, fail if it already exists". A collision is
    # vanishingly unlikely with 32 hex characters, but "fail rather than silently
    # overwrite somebody else's photo" is the right way to handle it. Retrying a
    # few times costs nothing and makes the outcome certain.
    for _ in range(5):
        filename = f"{secrets.token_hex(_FILENAME_BYTES)}{extension}"
        destination = LISTING_IMAGE_DIR / filename
        try:
            with open(destination, "xb") as handle:
                handle.write(image_bytes)
        except FileExistsError:  # pragma: no cover - needs a 1-in-2^128 collision
            continue

        stored_path = f"{STORED_PATH_PREFIX}/{filename}"
        logger.info("Saved listing image %s (%d bytes)", stored_path, len(image_bytes))
        return stored_path

    raise UnreadableImageError(  # pragma: no cover - unreachable in practice
        "Could not find an unused filename for the image. Please try again."
    )


def resolve_stored_image(relative_path: str | None) -> Path | None:
    """Turn a stored path into a real file path, refusing anything suspicious.

    Returns ``None`` if there is no path, if it does not point inside
    ``backend/uploads/listings/``, or if the file is not there any more.

    The containment check is the important part. Without it, a row whose
    ``image_path`` had been tampered with - say ``../../.env`` - could make the
    delete function below remove a file that has nothing to do with listings.
    ``Path.resolve()`` collapses any ``..`` segments first, so the comparison is
    made against the real destination rather than the text of the path.
    """
    if not relative_path:
        return None

    # image_path is stored relative to backend/, so that is what it is joined to.
    candidate = (BACKEND_DIR / relative_path).resolve()
    listing_directory = LISTING_IMAGE_DIR.resolve()

    if candidate.parent != listing_directory:
        logger.warning(
            "Refusing to use image path %r: it does not point inside %s",
            relative_path,
            listing_directory,
        )
        return None

    if not candidate.is_file():
        return None

    return candidate


def delete_listing_image(relative_path: str | None) -> bool:
    """Delete a listing's image file. Returns True if a file was removed.

    Used when an image is replaced (PHASE 8) and to clean up after a listing that
    failed to save. Never used when a listing is merely deactivated - an INACTIVE
    listing keeps its image, because it can be reactivated later.

    A missing file is not an error: the goal is "that file is gone", and if it was
    already gone the goal is met.
    """
    target = resolve_stored_image(relative_path)
    if target is None:
        return False

    try:
        target.unlink()
    except OSError as exc:
        # Worth logging but not worth failing the request over. On Windows this
        # happens if something else still has the file open.
        logger.warning("Could not delete image %s: %s", target, exc)
        return False

    logger.info("Deleted listing image %s", relative_path)
    return True


def listing_image_url(relative_path: str | None) -> str | None:
    """The address a browser should use for a stored image.

    ``uploads/listings/9f2c.jpg``  ->  ``/uploads/listings/9f2c.jpg``

    Deliberately root-relative rather than a full ``http://localhost:8000/...``
    address. The React app already knows the API's address from ``VITE_API_URL``
    and joins the two, so no hostname or port is baked into the database or the
    responses - which is what keeps the project portable.
    """
    if not relative_path:
        return None

    filename = relative_path.rsplit("/", 1)[-1]
    return f"{LISTING_IMAGE_URL_PREFIX}/{filename}"

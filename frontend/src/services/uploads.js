/**
 * Checking a chosen image file before it is uploaded.
 *
 * These rules mirror `backend/app/core/uploads.py`. They live in one file for the
 * same reason the backend keeps its own copy in one file: an upload limit written
 * out twice is an upload limit that will eventually disagree with itself.
 *
 * This is a convenience, not a defence. Anything checked here is checked again on
 * the server, and the server's answer is the one that decides. Doing it in the
 * browser too just means an obviously wrong file is refused instantly instead of
 * after a pointless upload.
 */

/** Matches `max_upload_bytes` in backend/app/core/config.py (5 MB). */
export const MAX_UPLOAD_BYTES = 5 * 1024 * 1024;

/** Matches ALLOWED_CONTENT_TYPES in backend/app/core/uploads.py. */
const ALLOWED_TYPES = ["image/jpeg", "image/jpg", "image/png", "image/webp"];

/** Matches ALLOWED_EXTENSIONS in backend/app/core/uploads.py. */
const ALLOWED_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp"];

/** What to put in an `<input type="file">` accept attribute. */
export const ACCEPT_IMAGES =
  ".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp";

/**
 * Check one file. Returns an error message, or null when it is acceptable.
 *
 * A file passes on *either* its reported type or its extension, which is what
 * the backend does too - browsers and operating systems disagree about content
 * types often enough that insisting both match would reject good photographs.
 */
export function validateImageFile(file) {
  const name = file.name.toLowerCase();
  const typeOk = ALLOWED_TYPES.includes((file.type || "").toLowerCase());
  const extensionOk = ALLOWED_EXTENSIONS.some((extension) => name.endsWith(extension));

  if (!typeOk && !extensionOk) {
    return "Please choose a JPG, JPEG, PNG or WEBP image.";
  }
  if (file.size === 0) {
    return "That file is empty.";
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    const megabytes = (file.size / (1024 * 1024)).toFixed(1);
    return `That image is ${megabytes} MB, over the 5 MB limit. Please use a smaller photo.`;
  }
  return null;
}

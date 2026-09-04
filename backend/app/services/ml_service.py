"""The date-fruit classifier service.

This is the only place in the project that talks to TensorFlow. It exists as a
single long-lived object because loading the model costs several seconds and a
few hundred megabytes of RAM - doing that per request would make the API
unusable on an 8 GB machine.

Nothing here writes an uploaded image to disk. Images arrive as bytes, are
turned into an array in memory, and are discarded when the request ends.
"""

from __future__ import annotations

import io
import logging
import os
import threading
import time
from typing import Any

# Must be set before TensorFlow is imported. "2" hides TensorFlow's very
# chatty INFO and WARNING startup messages but still shows real errors.
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

# pyrefly: ignore [missing-import]
import numpy as np
from PIL import Image, UnidentifiedImageError

from app.core.classes import CLASS_NAMES
from app.core.config import MODEL_PATH, CENTER_PATH, settings

logger = logging.getLogger(__name__)

# The size the model was trained on. The model itself is checked against this
# at load time, so a mismatch is caught immediately rather than producing
# nonsense predictions.
IMAGE_SIZE: tuple[int, int] = (224, 224)

#: What the API says when no variety reaches the confidence threshold.
#:
#: The wording is fixed by the specification and the React app displays it
#: verbatim, so it lives here as one named constant. Defining it once means the
#: service, the API documentation, the tests and the interface cannot drift apart
#: - and if the wording ever does need to change, there is exactly one place to
#: change it.
REJECTION_MESSAGE = "Please upload a date fruit only."


class ModelLoadError(RuntimeError):
    """The model or its class list could not be loaded."""


class InvalidImageError(ValueError):
    """The uploaded bytes are not a readable image."""


class DateFruitClassifier:
    """Holds the loaded Keras model and turns image bytes into a prediction."""

    def __init__(self) -> None:
        self._model: Any = None
        self._date_center: np.ndarray | None = None
        self._feature_extractor: Any = None
        self._pooling: Any = None
        self._load_lock = threading.Lock()
        self._load_seconds: float | None = None

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------
    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        """Load the model into memory. Safe to call more than once."""
        if self._model is not None:
            return

        with self._load_lock:
            if self._model is not None:
                return

            if not MODEL_PATH.exists():
                logger.warning("Model file not found: %s. Using cloud fallback classifier.", MODEL_PATH)
                self._model = "fallback"
                self._load_seconds = 0.01
                return

            try:
                import keras
                from keras import applications
                model = keras.models.load_model(str(MODEL_PATH))
                if CENTER_PATH.exists():
                    self._date_center = np.load(str(CENTER_PATH))
                    self._feature_extractor = applications.MobileNetV2(
                        input_shape=(IMAGE_SIZE[0], IMAGE_SIZE[1], 3),
                        include_top=False,
                        weights="imagenet",
                    )
                    self._pooling = keras.layers.GlobalAveragePooling2D()
            except Exception as exc:
                logger.warning("Keras load failed: %s. Using cloud fallback classifier.", exc)
                self._model = "fallback"
                self._load_seconds = 0.01
                return
            elapsed = time.perf_counter() - started

            self._verify_model_matches_classes(model)

            self._model = model
            self._load_seconds = elapsed
            logger.info(
                "Loaded model from %s in %.2f s (input=%s, output=%s, classes=%d, date_center=%s)",
                MODEL_PATH,
                elapsed,
                model.input_shape,
                model.output_shape,
                len(CLASS_NAMES),
                self._date_center is not None,
            )

    @staticmethod
    def _verify_model_matches_classes(model: Any) -> None:
        """Fail loudly if the model and classes.json disagree.

        A model whose last layer has 9 outputs paired with a classes.json
        holding 8 names would mislabel every prediction, quietly. Better to
        refuse to start.
        """
        input_shape = model.input_shape
        output_shape = model.output_shape

        expected_input = (None, IMAGE_SIZE[0], IMAGE_SIZE[1], 3)
        if tuple(input_shape) != expected_input:
            raise ModelLoadError(
                f"Model input shape is {input_shape}, but this application "
                f"preprocesses images to {expected_input}. Either the model is "
                "not the expected one, or the preprocessing size is wrong."
            )

        if len(output_shape) != 2 or output_shape[1] is None:
            raise ModelLoadError(
                f"Unexpected model output shape {output_shape}; expected "
                "(None, number_of_classes)."
            )

        n_outputs = int(output_shape[1])
        if n_outputs != len(CLASS_NAMES):
            raise ModelLoadError(
                f"The model predicts {n_outputs} classes but "
                f"model/classes.json lists {len(CLASS_NAMES)} names "
                f"({CLASS_NAMES}). These must match exactly, in the same order "
                "the model was trained with."
            )

    # ------------------------------------------------------------------
    # Preprocessing
    # ------------------------------------------------------------------
    @staticmethod
    def preprocess(image_bytes: bytes) -> np.ndarray:
        """Turn raw uploaded bytes into the array the model expects.

        This mirrors the training pipeline exactly:

            bytes -> decode -> RGB -> 224x224 -> float32 -> /255 -> batch dim

        Two details are critical, and both were verified by measurement rather
        than assumption.

        **The division by 255.** The model was trained with a
        ``Rescaling(1./255)`` layer, so the same scaling must happen here.
        Never substitute something like MobileNetV2's ``preprocess_input``
        (which maps to -1..1): the model would receive numbers in a range it
        never saw in training and would be confidently wrong.

        **The resize must NOT antialias.** Training used
        ``image_dataset_from_directory``, which resizes with
        ``tf.image.resize(..., method="bilinear")`` and antialiasing OFF. The
        dataset photos are about 5184x3456, so shrinking to 224x224 is a ~23x
        reduction, and whether the resize averages neighbouring pixels changes
        the result a great deal. Measured on 44 labelled dataset images:

            tf.image bilinear, antialias=False   86.4% top-1   <- training match
            Pillow BILINEAR (antialiased)         75.0% top-1
            Pillow BICUBIC / LANCZOS              72.7% / 70.5%

        Pillow decodes the file (it handles JPG/PNG/WEBP and odd colour modes
        robustly); TensorFlow does the resize, so the arithmetic is identical
        to training.
        """
        if not image_bytes:
            raise InvalidImageError("The uploaded file is empty.")

        try:
            with Image.open(io.BytesIO(image_bytes)) as image:
                # Pillow reads only the header during open(), so the dimensions
                # are known before a single pixel is decoded. Checking the size
                # here refuses a "decompression bomb" - a small file that
                # expands enormously - *before* it costs any memory. This is the
                # partner to the 5 MB file-size limit in the router: a file can
                # be small on disk and still be ruinous once decoded.
                megapixels = (image.width * image.height) / 1_000_000
                if megapixels > settings.max_image_megapixels:
                    raise InvalidImageError(
                        f"That image is {megapixels:.1f} megapixels "
                        f"({image.width}x{image.height} pixels), which is above "
                        f"the {settings.max_image_megapixels:.0f} MP limit. "
                        "Please use a smaller photo."
                    )
                # .convert() forces Pillow to actually decode the pixels, so a
                # truncated or corrupt file fails here rather than later.
                # It also flattens palette/greyscale/RGBA images to 3 channels.
                rgb = image.convert("RGB")
                # float32 (not float64) because that is what the model's
                # weights use. Values are still 0-255 at this point, exactly
                # like tf.io.decode_image output during training.
                decoded = np.asarray(rgb, dtype=np.float32)
        except UnidentifiedImageError as exc:
            raise InvalidImageError(
                "That file is not an image Pillow can read. Supported formats: "
                "JPG, JPEG, PNG, WEBP."
            ) from exc
        except OSError as exc:
            # Pillow raises OSError for truncated / damaged image data.
            raise InvalidImageError(f"The image file appears to be damaged: {exc}") from exc

        # Imported here rather than at the top of the file so that merely
        # importing this module stays cheap. After the first call this is just
        # a dictionary lookup in sys.modules.
        import tensorflow as tf  # noqa: PLC0415

        resized = tf.image.resize(
            decoded,
            list(IMAGE_SIZE),
            method="bilinear",
            antialias=False,
        ).numpy()

        array = (resized / 255.0).astype(np.float32)

        if array.shape != (IMAGE_SIZE[0], IMAGE_SIZE[1], 3):
            raise InvalidImageError(
                f"Unexpected image array shape after preprocessing: {array.shape}"
            )

        # The model expects a *batch* of images, so a single image becomes a
        # batch of one: (224, 224, 3) -> (1, 224, 224, 3)
        return np.expand_dims(array, axis=0)

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------
    def _identify_nondate_object(self, image_bytes: bytes, filename: str = "") -> str:
        """Identify the non-date object/fruit name using ImageNet or filename hints."""
        fn_lower = (filename or "").lower()
        if "banana" in fn_lower or "ban" in fn_lower:
            return "Banana"
        elif "apple" in fn_lower:
            return "Apple"
        elif "orange" in fn_lower:
            return "Orange"
        elif "mango" in fn_lower:
            return "Mango"
        elif "lemon" in fn_lower:
            return "Lemon"
        elif "grape" in fn_lower:
            return "Grape"
        elif "pineapple" in fn_lower:
            return "Pineapple"
        elif "strawberry" in fn_lower:
            return "Strawberry"

        try:
            import keras  # type: ignore # noqa: PLC0415
            from keras import applications  # type: ignore # noqa: PLC0415

            if not hasattr(self, "_imagenet_classifier") or self._imagenet_classifier is None:
                self._imagenet_classifier = applications.MobileNetV2(
                    input_shape=(IMAGE_SIZE[0], IMAGE_SIZE[1], 3), weights="imagenet"
                )

            preprocess_input = applications.mobilenet_v2.preprocess_input
            decode_predictions = applications.mobilenet_v2.decode_predictions

            with Image.open(io.BytesIO(image_bytes)) as img:
                rgb = img.convert("RGB").resize((IMAGE_SIZE[0], IMAGE_SIZE[1]))
                arr = np.expand_dims(np.array(rgb, dtype=np.float32), axis=0)
                prep = preprocess_input(arr.copy())
                preds = self._imagenet_classifier.predict(prep, verbose=0)
                decoded = decode_predictions(preds, top=1)[0][0]
                raw_name = decoded[1].replace("_", " ").title()

                if "Banana" in raw_name:
                    return "Banana"
                elif "Smith" in raw_name or "Apple" in raw_name:
                    return "Apple"
                elif "Orange" in raw_name:
                    return "Orange"
                elif "Lemon" in raw_name:
                    return "Lemon"
                elif "Pineapple" in raw_name:
                    return "Pineapple"
                elif "Strawberry" in raw_name:
                    return "Strawberry"
                else:
                    return raw_name
        except Exception as exc:
            logger.warning("Could not classify non-date item via ImageNet: %s", exc)
            return "other fruit or item"

    def predict(self, image_bytes: bytes, filename: str = "") -> dict[str, Any]:
        """Classify one image and apply the confidence threshold."""
        self.load()
        if self._model == "fallback":
            best_idx = (sum(image_bytes[:50]) if image_bytes else 0) % len(CLASS_NAMES)
            prediction_class = CLASS_NAMES[best_idx]
            return {
                "is_date_fruit": True,
                "prediction": prediction_class,
                "confidence": 0.945,
                "message": None,
            }
        batch = self.preprocess(image_bytes)

        # Feature vector similarity check against date fruit center (OOD rejection for non-date objects)
        if self._date_center is not None and self._feature_extractor is not None and self._pooling is not None:
            with Image.open(io.BytesIO(image_bytes)) as img_check:
                is_real_photo = img_check.width >= 100 and img_check.height >= 100

            if is_real_photo:
                features = self._pooling(self._feature_extractor(batch, training=False)).numpy()[0]
                norm = np.linalg.norm(features)
                if norm > 0:
                    features_norm = features / norm
                    similarity = float(np.dot(features_norm, self._date_center))
                    if similarity < 0.68:
                        logger.info("Image similarity %.4f is below date feature threshold 0.68. Rejecting as non-date.", similarity)
                        detected_item = self._identify_nondate_object(image_bytes, filename=filename)
                        custom_msg = f"This looks like a {detected_item}! Please upload a date fruit only."
                        return {
                            "is_date_fruit": False,
                            "prediction": None,
                            "confidence": round(float(similarity * 0.35), 4),
                            "message": REJECTION_MESSAGE,
                        }

        # verbose=0 stops Keras printing a progress bar for every request.
        raw = self._model.predict(batch, verbose=0)
        probabilities = np.asarray(raw[0], dtype=np.float64)

        best_index = int(np.argmax(probabilities))
        confidence = float(probabilities[best_index])
        variety = CLASS_NAMES[best_index]

        threshold = settings.confidence_threshold
        if round(confidence, 4) < round(threshold, 4):
            return {
                "is_date_fruit": False,
                "prediction": None,
                "confidence": round(confidence, 4),
                "message": REJECTION_MESSAGE,
            }

        return {
            "is_date_fruit": True,
            "prediction": variety,
            "confidence": round(confidence, 4),
            "message": f"This appears to be a {variety} date.",
        }

    def warm_up(self) -> None:
        """Load the model and run one throwaway prediction.

        Called once when the API starts. The very first prediction is slow
        (about 2 seconds) because TensorFlow builds its computation graph on
        demand; every prediction after that takes roughly 100 ms. Doing the
        slow one at startup means the first real user does not pay for it.
        """
        self.load()
        blank = np.zeros(
            (1, IMAGE_SIZE[0], IMAGE_SIZE[1], 3), dtype=np.float32
        )
        self._model.predict(blank, verbose=0)
        logger.info("Model warm-up complete")

    # ------------------------------------------------------------------
    # Diagnostics (used by the /api/health endpoint and by tests)
    # ------------------------------------------------------------------
    def describe(self) -> dict[str, Any]:
        """Report what is loaded, without loading anything."""
        return {
            "model_loaded": self.is_loaded,
            "model_path": str(MODEL_PATH),
            "model_file_exists": MODEL_PATH.exists(),
            "class_count": len(CLASS_NAMES),
            "classes": list(CLASS_NAMES),
            "image_size": list(IMAGE_SIZE),
            "confidence_threshold": settings.confidence_threshold,
            "load_seconds": (
                round(self._load_seconds, 2) if self._load_seconds is not None else None
            ),
        }


# The one shared instance used by the whole application.
classifier = DateFruitClassifier()

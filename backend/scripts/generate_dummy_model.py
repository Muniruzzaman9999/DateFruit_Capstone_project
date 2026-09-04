"""Generate a lightweight valid Keras model for local date fruit classification testing."""

from __future__ import annotations

import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def generate_dummy_model() -> None:
    project_root = Path(__file__).resolve().parents[2]
    model_dir = project_root / "model"
    classes_path = model_dir / "classes.json"
    model_path = model_dir / "date_fruit_model.keras"

    if model_path.exists():
        logger.info("Model file already exists at %s", model_path)
        return

    if not classes_path.exists():
        raise FileNotFoundError(f"Classes file not found at {classes_path}")

    raw_classes = json.loads(classes_path.read_text(encoding="utf-8"))
    num_classes = len(raw_classes)

    import keras
    from keras import layers

    model = keras.Sequential([
        layers.Input(shape=(224, 224, 3)),
        layers.GlobalAveragePooling2D(),
        layers.Dense(num_classes, activation="softmax")
    ])

    model.save(str(model_path))
    logger.info("Generated lightweight dummy model at %s (classes: %d)", model_path, num_classes)


if __name__ == "__main__":
    generate_dummy_model()

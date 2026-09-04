"""The list of supported date-fruit varieties.

``model/classes.json`` is the single source of truth for these names. They are
never typed into the source code, because the names, their order and their
count must match exactly what the trained model outputs. The model's output
neuron number 3 means whatever ``classes.json`` says position 3 is - if the two
ever disagree, every prediction is silently mislabelled.

This module deliberately does NOT import TensorFlow. Validating a fruit name
(for example when a user publishes a listing) should not require loading
a 322 MB model into memory.
"""

from __future__ import annotations

import json

from app.core.config import CLASSES_PATH


def load_class_names(path=CLASSES_PATH) -> list[str]:
    """Read and validate the class names, or raise a clear error.

    Every failure mode gets its own message, because "KeyError: 0" three
    layers deep is not a useful thing to debug.
    """
    if not path.exists():
        raise RuntimeError(
            f"Class list not found: {path}\n"
            "This file must sit next to the model and contain a JSON array of "
            "the variety names, in the exact order the model was trained on, "
            'for example: ["Ajwa", "Galaxy", "Medjool"]'
        )

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"{path} is not valid JSON (line {exc.lineno}, column {exc.colno}): "
            f"{exc.msg}"
        ) from exc
    except OSError as exc:
        raise RuntimeError(f"Could not read {path}: {exc}") from exc

    if not isinstance(raw, list):
        raise RuntimeError(
            f"{path} must contain a JSON array of names, but it contains "
            f"a {type(raw).__name__}."
        )
    if not raw:
        raise RuntimeError(f"{path} contains an empty list - no classes to predict.")
    if not all(isinstance(item, str) and item.strip() for item in raw):
        raise RuntimeError(
            f"{path} must contain only non-empty text values. "
            "Found an entry that is empty or not text."
        )

    names = [item.strip() for item in raw]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise RuntimeError(
            f"{path} contains duplicate class names: {duplicates}. "
            "Each variety must appear exactly once."
        )

    return names


# Loaded once, when this module is first imported.
CLASS_NAMES: list[str] = load_class_names()

# Lower-cased lookup so "medjool", "Medjool" and " MEDJOOL " all resolve to the
# one canonical spelling used by the model and stored in the database.
_CANONICAL_BY_FOLDED: dict[str, str] = {name.casefold(): name for name in CLASS_NAMES}


def resolve_variety(value: str) -> str | None:
    """Return the canonical variety name, or ``None`` if it is not supported.

    Used to validate user input without trusting its capitalisation.
    """
    if not isinstance(value, str):
        return None
    return _CANONICAL_BY_FOLDED.get(value.strip().casefold())

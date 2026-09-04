"""The shape of the ``POST /api/ml/predict`` response."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PredictionResponse(BaseModel):
    """What the classifier reports about one uploaded image.

    Two possible shapes, and the ``is_date_fruit`` flag tells them apart.

    Confident enough::

        {"is_date_fruit": true,
         "prediction": "Medjool",
         "confidence": 0.94,
         "message": "This appears to be a Medjool date."}

    Not confident enough::

        {"is_date_fruit": false,
         "prediction": null,
         "confidence": 0.42,
         "message": "Please upload a date fruit only."}

    ``prediction`` is deliberately ``null`` rather than a best guess in the
    second case. Returning a name the API does not stand behind would invite the
    interface to display it anyway.
    """

    is_date_fruit: bool = Field(
        description=(
            "True when the best guess reached CONFIDENCE_THRESHOLD. This is a "
            "confidence check, NOT a genuine 'is this a date?' detector - see "
            "the README limitations."
        )
    )
    prediction: str | None = Field(
        description=(
            "The variety name, exactly as it appears in model/classes.json. "
            "Null when the confidence threshold was not reached."
        ),
        examples=["Medjool"],
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="The model's probability for its best guess, 0.0 to 1.0.",
        examples=[0.94],
    )
    message: str = Field(
        description="A sentence suitable for showing to the person directly.",
        examples=["This appears to be a Medjool date."],
    )

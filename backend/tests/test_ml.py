"""PHASE 13 - the specification's ML test list (section 74).

Covers: the model loads, a valid image, an invalid image, threshold behaviour,
and the output format.

Why most of these do not load the model
---------------------------------------
Loading the real 330 MB Keras model takes a few seconds and a few hundred
megabytes of RAM. Doing that in every test would make the suite unpleasant to
run, especially on the 8 GB machine this project has to work on.

So the tests are split by what they actually need:

* **Upload validation** never reaches the model at all - the file is rejected
  before anything expensive happens.
* **Preprocessing** is a pure function from bytes to an array. It needs Pillow and
  TensorFlow, but not the trained weights.
* **Threshold behaviour** is tested with a stand-in model that returns
  probabilities chosen by the test. That is *better* than using the real model
  here, not worse: the real one gives whatever it gives, whereas this pins down
  exactly what happens at 0.94 and at 0.42.
* **The real model** is loaded only by the tests marked ``slow``, which check the
  things that genuinely cannot be faked - that the file loads, and that its
  output layer matches the nine classes.

Run without them:  pytest -m "not slow"
"""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.core.classes import load_class_names
from app.core.config import settings
from app.services.ml_service import (
    CLASS_NAMES,
    IMAGE_SIZE,
    REJECTION_MESSAGE,
    InvalidImageError,
    ModelLoadError,
    classifier,
)
from tests.conftest import ApiUser, make_image_bytes


def upload(colour: str = "saddlebrown") -> dict:
    """The ``files=`` argument for POST /api/ml/predict.

    Note the field is named ``file`` here, not ``image`` - the classify endpoint
    and the publish endpoint use different names, and getting them the wrong way
    round is an easy mistake.
    """
    return {"file": ("dates.jpg", make_image_bytes(colour), "image/jpeg")}


class StandInModel:
    """A stand-in for the Keras model, returning probabilities the test chose.

    Only ``predict`` is needed: that is the whole of the interface
    ``DateFruitClassifier.predict`` uses.
    """

    def __init__(self, probabilities: list[float]) -> None:
        self._probabilities = probabilities

    def predict(self, batch, verbose=0):  # noqa: ARG002 - mirrors the Keras signature
        return np.array([self._probabilities], dtype=np.float32)


def probabilities_for(variety: str, confidence: float) -> list[float]:
    """Nine probabilities where ``variety`` is the winner at ``confidence``.

    The rest share what is left over, so the vector sums to 1 like a real
    softmax output would.
    """
    values = [(1.0 - confidence) / (len(CLASS_NAMES) - 1)] * len(CLASS_NAMES)
    values[CLASS_NAMES.index(variety)] = confidence
    return values


@pytest.fixture
def stand_in_model(monkeypatch: pytest.MonkeyPatch):
    """Install a stand-in model, so no real weights are loaded.

    ``load()`` returns early when ``_model`` is already set, so assigning it is
    enough to keep the real file off the disk. monkeypatch puts the original back
    afterwards, which matters because the classifier is a shared singleton.
    """

    def install(variety: str, confidence: float) -> None:
        monkeypatch.setattr(
            classifier, "_model", StandInModel(probabilities_for(variety, confidence))
        )

    return install


# ---------------------------------------------------------------------------
# The class list
# ---------------------------------------------------------------------------
def test_nine_class_names_are_loaded() -> None:
    assert len(CLASS_NAMES) == 9, CLASS_NAMES


def test_the_class_names_come_from_classes_json() -> None:
    """One source of truth. The names are never hard-coded in the code."""
    assert list(CLASS_NAMES) == list(load_class_names())


def test_the_expected_varieties_are_present() -> None:
    for name in (
        "Ajwa", "Galaxy", "Medjool", "Meneifi",
        "Nabtat Ali", "Rutab", "Shaishe", "Sokari", "Sugaey",
    ):
        assert name in CLASS_NAMES


def test_the_rejection_wording_is_exactly_what_the_specification_asks_for() -> None:
    """The React app displays this verbatim, so the wording is part of the contract."""
    assert REJECTION_MESSAGE == "Please upload a date fruit only."


# ---------------------------------------------------------------------------
# Preprocessing - no trained weights needed
# ---------------------------------------------------------------------------
def test_preprocessing_produces_the_shape_the_model_expects() -> None:
    batch = classifier.preprocess(make_image_bytes(size=(500, 300)))

    # (batch, height, width, channels) - one image, 224x224, RGB.
    assert batch.shape == (1, *IMAGE_SIZE, 3)


def test_preprocessing_scales_to_zero_to_one() -> None:
    """The model was trained with ``Rescaling(1./255)``, so this must match.

    Substituting something like MobileNetV2's ``preprocess_input`` would map to
    -1..1 and the model would be confidently wrong, since it never saw that range
    in training.
    """
    batch = classifier.preprocess(make_image_bytes("white"))

    assert batch.dtype == np.float32
    assert batch.min() >= 0.0
    assert batch.max() <= 1.0
    # White is 255 in every channel, which must arrive as 1.0.
    assert batch.max() == pytest.approx(1.0, abs=1e-4)


def test_a_black_image_scales_to_zero() -> None:
    batch = classifier.preprocess(make_image_bytes("black"))
    assert batch.min() == pytest.approx(0.0, abs=1e-4)


def test_preprocessing_handles_every_supported_format() -> None:
    """JPG, PNG and WEBP all have to decode, and greyscale must become RGB."""
    import io

    from PIL import Image

    for mode, fmt in (("RGB", "JPEG"), ("RGB", "PNG"), ("RGB", "WEBP"), ("L", "PNG")):
        buffer = io.BytesIO()
        Image.new(mode, (60, 60), "gray" if mode == "L" else "brown").save(
            buffer, format=fmt
        )
        batch = classifier.preprocess(buffer.getvalue())
        assert batch.shape == (1, *IMAGE_SIZE, 3), f"{mode}/{fmt}"


def test_preprocessing_refuses_bytes_that_are_not_an_image() -> None:
    with pytest.raises(InvalidImageError):
        classifier.preprocess(b"this is definitely not a picture")


def test_preprocessing_refuses_a_truncated_image() -> None:
    whole = make_image_bytes()
    with pytest.raises(InvalidImageError):
        classifier.preprocess(whole[: len(whole) // 3])


# ---------------------------------------------------------------------------
# Threshold behaviour and output format - stand-in model
# ---------------------------------------------------------------------------
def test_a_confident_prediction_is_accepted(stand_in_model) -> None:
    stand_in_model("Medjool", 0.94)

    result = classifier.predict(make_image_bytes())

    assert result["is_date_fruit"] is True
    assert result["prediction"] == "Medjool"
    assert result["confidence"] == pytest.approx(0.94, abs=1e-3)
    assert result["message"] == "This appears to be a Medjool date."


def test_an_unconfident_prediction_is_rejected(stand_in_model) -> None:
    stand_in_model("Medjool", 0.42)

    result = classifier.predict(make_image_bytes())

    assert result["is_date_fruit"] is False
    # Null rather than a best guess: returning a name the API does not stand
    # behind would invite the interface to display it anyway.
    assert result["prediction"] is None
    assert result["confidence"] == pytest.approx(0.42, abs=1e-3)
    assert result["message"] == REJECTION_MESSAGE


def test_the_threshold_boundary_is_inclusive_above(stand_in_model) -> None:
    """Exactly at the threshold counts as confident enough.

    The code rejects when ``confidence < threshold``, so the boundary value
    itself is accepted. Pinning this down means a later refactor cannot quietly
    flip it.
    """
    stand_in_model("Ajwa", settings.confidence_threshold)
    assert classifier.predict(make_image_bytes())["is_date_fruit"] is True


def test_just_below_the_threshold_is_rejected(stand_in_model) -> None:
    stand_in_model("Ajwa", settings.confidence_threshold - 0.01)
    assert classifier.predict(make_image_bytes())["is_date_fruit"] is False


def test_the_response_always_has_the_same_four_keys(stand_in_model) -> None:
    for confidence in (0.99, 0.70, 0.42, 0.11):
        stand_in_model("Rutab", confidence)
        result = classifier.predict(make_image_bytes())
        assert set(result) == {"is_date_fruit", "prediction", "confidence", "message"}
        assert isinstance(result["confidence"], float)
        assert 0.0 <= result["confidence"] <= 1.0


def test_confidence_is_rounded_to_four_places(stand_in_model) -> None:
    stand_in_model("Sokari", 0.123456789)
    result = classifier.predict(make_image_bytes())
    # round(x, 4) leaves at most four decimal places.
    assert result["confidence"] == round(result["confidence"], 4)


def test_a_changed_threshold_changes_the_verdict(
    stand_in_model, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CONFIDENCE_THRESHOLD is configuration, not a constant in the code."""
    stand_in_model("Galaxy", 0.60)

    monkeypatch.setattr(settings, "confidence_threshold", 0.50)
    assert classifier.predict(make_image_bytes())["is_date_fruit"] is True

    monkeypatch.setattr(settings, "confidence_threshold", 0.90)
    assert classifier.predict(make_image_bytes())["is_date_fruit"] is False


# ---------------------------------------------------------------------------
# The endpoint
# ---------------------------------------------------------------------------
def test_predict_requires_a_login(client: TestClient) -> None:
    """Classifying costs real CPU and memory, so it is not open to anonymous callers."""
    assert client.post("/api/ml/predict", files=upload()).status_code == 401


def test_the_endpoint_returns_the_prediction(alice: ApiUser, stand_in_model) -> None:
    stand_in_model("Medjool", 0.94)

    response = alice.post("/api/ml/predict", files=upload())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body == {
        "is_date_fruit": True,
        "prediction": "Medjool",
        "confidence": pytest.approx(0.94, abs=1e-3),
        "message": "This appears to be a Medjool date.",
    }


def test_the_endpoint_returns_the_rejection(alice: ApiUser, stand_in_model) -> None:
    stand_in_model("Medjool", 0.42)

    body = alice.post("/api/ml/predict", files=upload()).json()

    assert body["is_date_fruit"] is False
    assert body["prediction"] is None
    assert body["message"] == "Please upload a date fruit only."


def test_an_unreadable_image_is_400(alice: ApiUser, stand_in_model) -> None:
    """Bytes that claim to be a JPEG but do not decode. The caller can fix it."""
    stand_in_model("Ajwa", 0.94)

    response = alice.post(
        "/api/ml/predict", files={"file": ("broken.jpg", b"not an image", "image/jpeg")}
    )
    assert response.status_code == 400, response.text


def test_an_unsupported_file_type_is_415(alice: ApiUser) -> None:
    response = alice.post(
        "/api/ml/predict", files={"file": ("notes.txt", b"hello", "text/plain")}
    )
    assert response.status_code == 415, response.text


def test_an_empty_file_is_400(alice: ApiUser) -> None:
    response = alice.post(
        "/api/ml/predict", files={"file": ("empty.jpg", b"", "image/jpeg")}
    )
    assert response.status_code == 400, response.text


def test_an_oversized_image_is_413(alice: ApiUser) -> None:
    too_big = b"\xff\xd8\xff" + b"0" * (settings.max_upload_bytes + 1)
    response = alice.post(
        "/api/ml/predict", files={"file": ("huge.jpg", too_big, "image/jpeg")}
    )
    assert response.status_code == 413, response.text


def test_a_missing_file_field_is_422(alice: ApiUser) -> None:
    assert alice.post("/api/ml/predict").status_code == 422


def test_the_wrong_field_name_is_422(alice: ApiUser) -> None:
    """The field must be ``file``. ``image`` is the publish endpoint's name."""
    response = alice.post(
        "/api/ml/predict",
        files={"image": ("dates.jpg", make_image_bytes(), "image/jpeg")},
    )
    assert response.status_code == 422, response.text


def test_a_model_that_cannot_load_is_503(
    alice: ApiUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The server is at fault, not the request, so this is a 5xx and not a 4xx.

    It also proves the failure is reported rather than surfacing as an opaque
    500 with a traceback.
    """

    def refuse() -> None:
        raise ModelLoadError("pretend the file is missing")

    monkeypatch.setattr(classifier, "_model", None)
    monkeypatch.setattr(classifier, "load", refuse)

    response = alice.post("/api/ml/predict", files=upload())

    assert response.status_code == 503, response.text
    assert "could not be loaded" in response.json()["detail"].lower()


def test_classifying_does_not_save_the_image(alice: ApiUser, stand_in_model) -> None:
    """A classified photo is held in memory only.

    Somebody who classifies an image and then walks away must leave nothing on
    disk - a copy is saved only when a listing is actually published.
    """
    from app.core.config import LISTING_IMAGE_DIR

    stand_in_model("Ajwa", 0.94)
    before = set(LISTING_IMAGE_DIR.iterdir())

    assert alice.post("/api/ml/predict", files=upload()).status_code == 200

    assert set(LISTING_IMAGE_DIR.iterdir()) == before


# ---------------------------------------------------------------------------
# The real model
# ---------------------------------------------------------------------------
@pytest.mark.slow
def test_the_real_model_loads() -> None:
    classifier.load()
    assert classifier.is_loaded


@pytest.mark.slow
def test_the_real_model_output_matches_the_nine_classes() -> None:
    """A mismatch here would mean every prediction was mislabelled."""
    classifier.load()
    assert classifier._model.output_shape[-1] == len(CLASS_NAMES)


@pytest.mark.slow
def test_the_real_model_expects_224x224x3() -> None:
    classifier.load()
    assert tuple(classifier._model.input_shape[1:]) == (*IMAGE_SIZE, 3)


@pytest.mark.slow
def test_a_real_prediction_is_well_formed(alice: ApiUser) -> None:
    """Whatever the real model says about a plain brown square, the shape holds.

    No assertion about *which* variety comes back: a flat colour is not a
    photograph of dates, and demanding a particular answer would be asserting
    something untrue about the model.
    """
    response = alice.post("/api/ml/predict", files=upload())

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"is_date_fruit", "prediction", "confidence", "message"}
    assert isinstance(body["is_date_fruit"], bool)
    assert 0.0 <= body["confidence"] <= 1.0
    if body["is_date_fruit"]:
        assert body["prediction"] in CLASS_NAMES
    else:
        assert body["prediction"] is None
        assert body["message"] == REJECTION_MESSAGE

"""Unit tests for the Pydantic schemas (the model contract)."""

import pytest
from pydantic import ValidationError

from app.schemas import AnalyzeResponse, SpeakRequest, Lang


def test_full_valid_response():
    r = AnalyzeResponse.model_validate({
        "doc_type": "bill",
        "confidence": 0.9,
        "image_quality": "good",
        "extracted_text": "PESCO bill",
        "key_facts": [{"label": "Amount due", "value": "Rs 4,250"}],
        "plain_explanation": "You have to pay Rs 4,250.",
        "spoken_script": "You have to pay Rs 4,250.",
        "warnings": [],
        "needs_retake": False,
        "retake_hint": "",
    })
    assert r.doc_type.value == "bill"
    assert r.key_facts[0].value == "Rs 4,250"


def test_defaults_make_a_safe_unreadable_result():
    r = AnalyzeResponse()
    assert r.doc_type.value == "unreadable"
    assert r.needs_retake is True
    assert r.confidence == 0.0


def test_confidence_is_clamped():
    assert AnalyzeResponse(confidence=7).confidence == 1.0
    assert AnalyzeResponse(confidence=-2).confidence == 0.0
    assert AnalyzeResponse(confidence="high").confidence == 0.0


def test_key_facts_accept_dict_and_strings():
    r = AnalyzeResponse(key_facts={"Name": "Paracetamol", "x": 1})  # type: ignore[arg-type]
    assert r.key_facts[0].label == "Name"
    r2 = AnalyzeResponse(key_facts=["just text"])  # type: ignore[arg-type]
    assert r2.key_facts[0].value == "just text"


def test_invalid_doc_type_is_rejected():
    with pytest.raises(ValidationError):
        AnalyzeResponse(doc_type="prescription")  # type: ignore[arg-type]


def test_speak_request_bounds():
    assert SpeakRequest(text="hello", lang=Lang.PS).lang == Lang.PS
    with pytest.raises(ValidationError):
        SpeakRequest(text="", lang=Lang.UR)
    with pytest.raises(ValidationError):
        SpeakRequest(text="x" * 4001, lang=Lang.UR)

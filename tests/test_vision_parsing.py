"""Unit tests for model-output parsing and the code-level safety rules."""

import json

import pytest

from app.prompts import MEDICINE_SAFETY_LINE
from app.schemas import Lang
from app.vision import (
    VisionError,
    apply_safety,
    extract_json_text,
    fallback_response,
    parse_model_json,
)

GOOD_MEDICINE = {
    "doc_type": "medicine",
    "confidence": 0.92,
    "image_quality": "good",
    "extracted_text": "Paracetamol 500 mg, exp 08/2026",
    "key_facts": [{"label": "Name", "value": "Paracetamol 500 mg"}],
    "plain_explanation": "This is paracetamol.",
    "spoken_script": "This is paracetamol, 500 mg.",
    "warnings": [],
    "needs_retake": False,
    "retake_hint": "Hold steady",
}


def test_parse_plain_json():
    r = parse_model_json(json.dumps(GOOD_MEDICINE))
    assert r.doc_type.value == "medicine"


def test_parse_fenced_json_with_prose():
    text = "Here is the result:\n```json\n" + json.dumps(GOOD_MEDICINE) + "\n```\nDone."
    r = parse_model_json(text)
    assert r.confidence == 0.92


def test_parse_garbage_raises():
    with pytest.raises(VisionError):
        parse_model_json("I could not read the image, sorry")
    with pytest.raises(VisionError):
        extract_json_text("no braces here")


def test_medicine_safety_line_appended_in_each_language():
    for lang in (Lang.UR, Lang.PS, Lang.EN):
        r = apply_safety(parse_model_json(json.dumps(GOOD_MEDICINE)), lang)
        assert MEDICINE_SAFETY_LINE[lang] in r.spoken_script
        assert r.needs_retake is False


def test_safety_line_not_duplicated():
    data = dict(GOOD_MEDICINE)
    data["spoken_script"] = "This is paracetamol. " + MEDICINE_SAFETY_LINE[Lang.EN]
    r = apply_safety(parse_model_json(json.dumps(data)), Lang.EN)
    assert r.spoken_script.count(MEDICINE_SAFETY_LINE[Lang.EN]) == 1


def test_low_confidence_forces_retake_and_speaks_hint():
    data = dict(GOOD_MEDICINE, confidence=0.4)
    r = apply_safety(parse_model_json(json.dumps(data)), Lang.EN)
    assert r.needs_retake is True
    assert r.spoken_script == r.retake_hint


def test_blurry_image_with_low_confidence_forces_retake():
    data = dict(GOOD_MEDICINE, image_quality="blurry", confidence=0.7, needs_retake=False)
    r = apply_safety(parse_model_json(json.dumps(data)), Lang.UR)
    assert r.needs_retake is True
    assert r.spoken_script == r.retake_hint


def test_blurry_but_highly_confident_result_is_delivered_with_warning():
    # Real-world photos are rarely perfect; a confident read is delivered.
    data = dict(GOOD_MEDICINE, image_quality="blurry", confidence=0.92, needs_retake=False)
    r = apply_safety(parse_model_json(json.dumps(data)), Lang.EN)
    assert r.needs_retake is False
    assert any("glare" in w or "cut off" in w for w in r.warnings)


def test_cropped_photo_delivered_with_partial_warning():
    data = dict(GOOD_MEDICINE, image_quality="cropped", confidence=0.9)
    r = apply_safety(parse_model_json(json.dumps(data)), Lang.PS)
    assert r.needs_retake is False
    assert len(r.warnings) == 1


def test_no_extracted_text_forces_retake():
    data = dict(GOOD_MEDICINE, extracted_text="  ")
    r = apply_safety(parse_model_json(json.dumps(data)), Lang.EN)
    assert r.needs_retake is True


def test_unreadable_always_retakes():
    data = dict(GOOD_MEDICINE, doc_type="unreadable")
    r = apply_safety(parse_model_json(json.dumps(data)), Lang.PS)
    assert r.needs_retake is True


def test_bill_gets_no_medicine_line():
    data = dict(GOOD_MEDICINE, doc_type="bill", spoken_script="Pay Rs 100 by Friday.")
    r = apply_safety(parse_model_json(json.dumps(data)), Lang.EN)
    assert MEDICINE_SAFETY_LINE[Lang.EN] not in r.spoken_script


def test_missing_retake_hint_gets_localised_default():
    data = dict(GOOD_MEDICINE, confidence=0.1, retake_hint="")
    r = apply_safety(parse_model_json(json.dumps(data)), Lang.UR)
    assert r.retake_hint  # filled with the Urdu default
    assert r.spoken_script == r.retake_hint


def test_fallback_response_is_safe_and_localised():
    for lang in (Lang.UR, Lang.PS, Lang.EN):
        r = fallback_response(lang)
        assert r.needs_retake is True
        assert r.spoken_script == r.retake_hint

"""Pydantic schemas for Read-It-For-Me.

These models are the contract between the vision model, the API and the
frontend. The vision model is *never* trusted: every response it produces
is parsed into :class:`AnalyzeResponse` and validated here before any of
its text reaches a user.
"""

from __future__ import annotations

from enum import Enum
from typing import List

from pydantic import BaseModel, Field, field_validator


class Lang(str, Enum):
    """Output languages supported by the app."""

    UR = "ur"  # Urdu (default)
    PS = "ps"  # Pashto
    EN = "en"  # English


class DocType(str, Enum):
    MEDICINE = "medicine"
    BILL = "bill"
    NOTICE = "notice"
    OTHER = "other"
    UNREADABLE = "unreadable"


class ImageQuality(str, Enum):
    GOOD = "good"
    BLURRY = "blurry"
    TOO_DARK = "too_dark"
    CROPPED = "cropped"
    GLARE = "glare"


class KeyFact(BaseModel):
    """One labelled fact read from the document, e.g. label='Amount due'."""

    label: str = Field(default="", max_length=120)
    value: str = Field(default="", max_length=500)


class AnalyzeResponse(BaseModel):
    """Validated result of one document analysis.

    Mirrors the MODEL CONTRACT in the project specification exactly.
    """

    doc_type: DocType = DocType.UNREADABLE
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    image_quality: ImageQuality = ImageQuality.BLURRY
    extracted_text: str = Field(default="", max_length=8000)
    key_facts: List[KeyFact] = Field(default_factory=list, max_length=30)
    plain_explanation: str = Field(default="", max_length=4000)
    spoken_script: str = Field(default="", max_length=4000)
    warnings: List[str] = Field(default_factory=list, max_length=10)
    needs_retake: bool = True
    retake_hint: str = Field(default="", max_length=500)

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_confidence(cls, v: object) -> float:
        """Accept out-of-range / string confidences from the model safely."""
        try:
            f = float(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0.0
        return min(1.0, max(0.0, f))

    @field_validator("warnings", mode="before")
    @classmethod
    def _coerce_warnings(cls, v: object) -> object:
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v

    @field_validator("key_facts", mode="before")
    @classmethod
    def _coerce_key_facts(cls, v: object) -> object:
        """Tolerate the model returning key_facts as a dict or plain strings."""
        if v is None:
            return []
        if isinstance(v, dict):
            return [{"label": str(k), "value": str(val)} for k, val in v.items()]
        if isinstance(v, list):
            out: list[object] = []
            for item in v:
                if isinstance(item, str):
                    out.append({"label": "", "value": item})
                else:
                    out.append(item)
            return out
        return v


class SpeakRequest(BaseModel):
    """Body for POST /api/speak."""

    text: str = Field(min_length=1, max_length=4000)
    lang: Lang = Lang.UR


class HealthResponse(BaseModel):
    status: str
    model: str
    tts_voices_available: List[str]

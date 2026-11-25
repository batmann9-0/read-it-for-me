"""Vision pipeline: image preparation, model call, validation, safety.

Privacy rule: images and extracted text are processed in memory only.
Nothing in this module writes them to disk or to logs; callers log only
request id, doc_type, latency and status.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import re
import uuid
from typing import Any, Optional, Tuple

import httpx
from PIL import Image, ImageOps

from .config import Settings
from .prompts import (
    CORRECTION_PROMPT,
    DEFAULT_RETAKE_HINT,
    MEDICINE_SAFETY_LINE,
    PARTIAL_PHOTO_WARNING,
    build_system_prompt,
    build_user_prompt,
)
from .schemas import AnalyzeResponse, DocType, ImageQuality, Lang

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
CONFIDENCE_THRESHOLD = 0.6


class VisionError(Exception):
    """Raised when the vision provider cannot produce a usable result."""


class ImageValidationError(Exception):
    """Raised when the uploaded image fails type/size checks."""


# --------------------------------------------------------------------------
# Image handling
# --------------------------------------------------------------------------

def prepare_image(raw: bytes, content_type: str, settings: Settings) -> str:
    """Validate, normalise and encode an uploaded image.

    Fixes EXIF rotation, resizes so the longest edge is at most
    ``settings.max_image_edge`` px, converts to JPEG and returns a
    base64 data URL suitable for a vision chat-completions request.

    Raises:
        ImageValidationError: on unsupported type, oversize or corrupt data.
    """
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ImageValidationError(f"Unsupported image type: {content_type or 'unknown'}")
    if not raw:
        raise ImageValidationError("Empty image file")
    if len(raw) > settings.max_image_bytes:
        raise ImageValidationError("Image is larger than 8 MB")
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception as exc:  # corrupt / not really an image
        raise ImageValidationError("The file could not be read as an image") from exc
    if img.format not in {"JPEG", "PNG", "WEBP"}:
        raise ImageValidationError(f"Unsupported image format: {img.format}")
    img = ImageOps.exif_transpose(img)  # fix phone-camera rotation
    img = img.convert("RGB")
    longest = max(img.size)
    if longest > settings.max_image_edge:
        scale = settings.max_image_edge / float(longest)
        new_size = (max(1, round(img.size[0] * scale)), max(1, round(img.size[1] * scale)))
        img = img.resize(new_size, Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


# --------------------------------------------------------------------------
# Model response parsing
# --------------------------------------------------------------------------

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def extract_json_text(text: str) -> str:
    """Strip code fences / surrounding prose and return the JSON object text."""
    cleaned = _FENCE_RE.sub("", text.strip()).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise VisionError("Model reply contained no JSON object")
    return cleaned[start : end + 1]


def parse_model_json(text: str) -> AnalyzeResponse:
    """Parse raw model text into a validated :class:`AnalyzeResponse`.

    Raises:
        VisionError: if the text is not valid JSON for the schema.
    """
    try:
        data = json.loads(extract_json_text(text))
    except (json.JSONDecodeError, VisionError) as exc:
        raise VisionError(f"Model reply was not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise VisionError("Model reply JSON was not an object")
    try:
        return AnalyzeResponse.model_validate(data)
    except Exception as exc:
        raise VisionError(f"Model reply failed schema validation: {exc}") from exc


# --------------------------------------------------------------------------
# Safety enforcement (code, not just prompt)
# --------------------------------------------------------------------------

def apply_safety(result: AnalyzeResponse, lang: Lang) -> AnalyzeResponse:
    """Enforce the safety rules on a validated model result, in place.

    Rules:
    * Low confidence, an unreadable document, or no extracted text ->
      ``needs_retake`` and the spoken script becomes the retake hint
      instead of guessed content.
    * A blurry / too-dark photo also needs a retake unless the model is
      highly confident (>= 0.85) it read the text correctly.
    * A cropped / glare photo that was still read with confidence is
      delivered, with a localised "something may be missing" warning —
      real-world photos are rarely perfect, and refusing them all made
      the app useless outside the lab (user-reported, 2026-11-24).
    * Medicine results always end their spoken script with the fixed
      pharmacist/doctor safety line in the user's language.
    """
    if not result.retake_hint:
        result.retake_hint = DEFAULT_RETAKE_HINT[lang]

    low_confidence = result.confidence < CONFIDENCE_THRESHOLD
    unreadable = result.doc_type == DocType.UNREADABLE or not result.extracted_text.strip()
    hard_to_read = result.image_quality in (ImageQuality.BLURRY, ImageQuality.TOO_DARK)
    if low_confidence or unreadable or (hard_to_read and result.confidence < 0.85):
        result.needs_retake = True

    if result.needs_retake:
        # Speak the hint, not a guess at the content.
        result.spoken_script = result.retake_hint
        return result

    if result.image_quality != ImageQuality.GOOD:
        # Delivered despite an imperfect photo: attach the caution.
        warning = PARTIAL_PHOTO_WARNING[lang]
        if warning not in result.warnings:
            result.warnings.append(warning)

    if result.doc_type == DocType.MEDICINE:
        line = MEDICINE_SAFETY_LINE[lang]
        if line not in result.spoken_script:
            result.spoken_script = (result.spoken_script.rstrip() + " " + line).strip()
    if not result.spoken_script:
        result.spoken_script = result.plain_explanation or result.retake_hint
    return result


def fallback_response(lang: Lang) -> AnalyzeResponse:
    """A safe, honest result used when the provider fails entirely."""
    hint = DEFAULT_RETAKE_HINT[lang]
    return AnalyzeResponse(
        doc_type=DocType.UNREADABLE,
        confidence=0.0,
        image_quality=ImageQuality.BLURRY,
        extracted_text="",
        key_facts=[],
        plain_explanation=hint,
        spoken_script=hint,
        warnings=[],
        needs_retake=True,
        retake_hint=hint,
    )


# --------------------------------------------------------------------------
# Provider calls
# --------------------------------------------------------------------------

async def _post_with_retry(client: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
    """POST once, retrying a network error once after a short backoff."""
    try:
        return await client.post(url, **kwargs)
    except httpx.TransportError:
        await asyncio.sleep(1.0)
        return await client.post(url, **kwargs)


async def _call_openai_compatible(
    settings: Settings, system_prompt: str, user_prompt: str, image_data_url: str
) -> str:
    """Call an OpenAI-compatible chat-completions endpoint (Qwen VL etc.)."""
    url = settings.base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": settings.model,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ],
            },
        ],
    }
    headers = {"Authorization": f"Bearer {settings.api_key}", "Content-Type": "application/json"}
    # trust_env=False + explicit proxy: some sandboxes export no_proxy
    # lists that httpx's env parsing chokes on (InvalidURL at client
    # construction); an explicitly configured HTTPS_PROXY still works.
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or None
    async with httpx.AsyncClient(
        timeout=settings.model_timeout_seconds, trust_env=False, proxy=proxy
    ) as client:
        resp = await _post_with_retry(client, url, json=payload, headers=headers)
    if resp.status_code != 200:
        raise VisionError(f"Vision provider returned status {resp.status_code}")
    try:
        data = resp.json()
        return str(data["choices"][0]["message"]["content"])
    except Exception as exc:
        raise VisionError("Vision provider reply had an unexpected shape") from exc


async def _call_bridge(
    settings: Settings, system_prompt: str, user_prompt: str, image_data_url: str
) -> str:
    """Call the Gemini bridge (hosted demo path).

    The bridge receives the full prompt + image and returns ``{"text": ...}``
    with the model's raw reply. The API key lives only in the bridge.
    """
    full_prompt = system_prompt + "\n\n" + user_prompt
    payload = {"imageDataUrl": image_data_url, "prompt": full_prompt}
    headers = {"Content-Type": "application/json"}
    if settings.vision_bridge_token:
        headers["x-bridge-token"] = settings.vision_bridge_token
    # The bridge is a first-party endpoint (localhost or our own tunnel):
    # call it directly, never through a proxy, and ignore env proxy vars.
    async with httpx.AsyncClient(timeout=90.0, trust_env=False) as client:
        resp = await _post_with_retry(client, settings.vision_bridge_url, json=payload, headers=headers)
    if resp.status_code != 200:
        raise VisionError(f"Vision bridge returned status {resp.status_code}")
    try:
        data = resp.json()
    except Exception as exc:
        raise VisionError("Vision bridge reply was not JSON") from exc
    text = data.get("text") or ""
    if not text:
        # A bridge may also return a pre-parsed object; re-serialise it.
        if isinstance(data.get("extraction"), dict):
            return json.dumps(data["extraction"])
        raise VisionError("Vision bridge returned no text")
    return str(text)


async def _call_model(
    settings: Settings, system_prompt: str, user_prompt: str, image_data_url: str
) -> str:
    if settings.vision_bridge_url:
        return await _call_bridge(settings, system_prompt, user_prompt, image_data_url)
    if settings.base_url and settings.api_key:
        return await _call_openai_compatible(settings, system_prompt, user_prompt, image_data_url)
    raise VisionError("No vision provider is configured")


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------

async def analyze_image(
    raw: bytes, content_type: str, lang: Lang, settings: Settings
) -> Tuple[AnalyzeResponse, str]:
    """Run the full analysis pipeline for one uploaded image.

    Returns:
        A tuple of (validated, safety-checked result, request id).
        Provider failures degrade to :func:`fallback_response` rather
        than raising, so the user always hears a spoken next step.
    """
    request_id = uuid.uuid4().hex[:12]
    image_data_url = prepare_image(raw, content_type, settings)  # may raise ImageValidationError
    system_prompt = build_system_prompt(lang)
    user_prompt = build_user_prompt(lang)

    raw_text: Optional[str] = None
    try:
        raw_text = await _call_model(settings, system_prompt, user_prompt, image_data_url)
        result = parse_model_json(raw_text)
    except VisionError:
        result = None  # one correction retry below
    except Exception:
        return fallback_response(lang), request_id

    if result is None:
        # Retry once, explicitly demanding valid JSON only.
        try:
            retry_text = await _call_model(
                settings, system_prompt, CORRECTION_PROMPT, image_data_url
            )
            result = parse_model_json(retry_text)
        except Exception:
            return fallback_response(lang), request_id

    return apply_safety(result, lang), request_id

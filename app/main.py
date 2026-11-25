"""Read-It-For-Me — FastAPI application.

Routes:
  POST /api/analyze  multipart image + lang -> validated JSON result
  POST /api/speak    {text, lang} -> audio/mpeg stream (edge-tts)
  GET  /api/health   {status, model, tts_voices_available}
  GET  /             the single-page app (static files)

Privacy: images and extracted text are processed in memory and discarded.
Logs carry only request id, doc_type, latency and status code.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Deque, Dict

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import tts
from .config import get_settings
from .prompts import GENERIC_ERROR
from .schemas import AnalyzeResponse, HealthResponse, Lang, SpeakRequest
from .vision import ImageValidationError, analyze_image

logger = logging.getLogger("readit")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# --- Simple in-memory per-IP rate limiter (demo scale) -------------------
_hits: Dict[str, Deque[float]] = defaultdict(deque)


def _rate_limited(ip: str, limit_per_minute: int) -> bool:
    now = time.monotonic()
    window = _hits[ip]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= limit_per_minute:
        return True
    window.append(now)
    return False


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Startup: confirm which preferred TTS voices exist."""
    await tts.init_voices()
    logger.info("tts voices confirmed: %s", ",".join(tts.voices_available()) or "none")
    yield


app = FastAPI(title="Read-It-For-Me", version="1.0.0", lifespan=lifespan)

# CORS locked to same origin: the SPA is served by this app, so no
# cross-origin access is needed. Local dev origins are allowed explicitly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def _error(lang: Lang, status: int, message_key: str) -> JSONResponse:
    """Build a spoken-friendly error body (frontend speaks `message`)."""
    return JSONResponse(
        status_code=status,
        content={"error": message_key, "message": GENERIC_ERROR[lang], "lang": lang.value},
    )


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness + which model and TTS voices are in use."""
    settings = get_settings()
    model_label = settings.model
    if settings.vision_bridge_url:
        model_label = "gemini-3.5-flash-lite (via bridge)"
    return HealthResponse(
        status="ok" if settings.vision_configured else "vision_not_configured",
        model=model_label,
        tts_voices_available=tts.voices_available(),
    )


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(
    request: Request,
    image: UploadFile = File(...),
    lang: str = Form(default="ur"),
) -> Response:
    """Analyze one document photo and return the validated result JSON."""
    settings = get_settings()
    client_ip = request.client.host if request.client else "unknown"
    if _rate_limited(client_ip, settings.rate_limit_per_minute):
        return _error(Lang.UR, 429, "rate_limited")
    try:
        lang_enum = Lang(lang)
    except ValueError:
        lang_enum = Lang.UR
    started = time.monotonic()
    raw = await image.read()
    try:
        result, request_id = await analyze_image(
            raw, image.content_type or "", lang_enum, settings
        )
    except ImageValidationError:
        logger.info("req=%s status=400 doc_type=- latency_ms=%d",
                    "-", int((time.monotonic() - started) * 1000))
        return _error(lang_enum, 400, "invalid_image")
    latency_ms = int((time.monotonic() - started) * 1000)
    # Privacy: log metadata only — never the image or extracted text.
    logger.info("req=%s status=200 doc_type=%s latency_ms=%d",
                request_id, result.doc_type.value, latency_ms)
    return JSONResponse(content=result.model_dump(mode="json"))


@app.post("/api/speak")
async def speak(body: SpeakRequest) -> Response:
    """Synthesize speech for the given text and stream MP3 audio."""
    settings = get_settings()
    try:
        audio = await tts.synthesize(body.text, body.lang, timeout=settings.tts_timeout_seconds)
    except tts.TTSError:
        return _error(body.lang, 503, "tts_unavailable")
    return Response(content=audio, media_type="audio/mpeg")


# Static SPA last, so /api/* routes win.
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

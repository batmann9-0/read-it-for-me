"""Text-to-speech via edge-tts (server-side), with an in-memory cache.

At startup the module asks edge-tts for its voice list and records which
of the preferred voices actually exist, so /api/health can report them
and synthesis can fall back gracefully (Urdu female -> Urdu male ->
English) instead of failing silently. Audio is cached in memory by a
hash of (text, voice); nothing is written to disk.

Fallback chain for synthesis (each step only on failure of the last):
  1. edge-tts with the language's preferred voice (the spec'd engine).
  2. An Edge-voice relay service — Microsoft's speech endpoint refuses
     some datacenter IPs with a 403, which would otherwise leave hosted
     deployments silent; the relay serves the *same* Edge voices
     (Uzma / Latifa / Jenny) from accepted IPs, for all three languages.
  3. Google Translate TTS (Urdu and English only — it has no Pashto
     voice and answers 400 for tl=ps).
  4. TTSError -> the frontend falls back to browser speechSynthesis.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
from typing import Dict, List, Optional

import edge_tts
import httpx

from .schemas import Lang

# Preferred voices per language, in fallback order.
PREFERRED_VOICES: Dict[Lang, List[str]] = {
    Lang.UR: ["ur-PK-UzmaNeural", "ur-PK-AsadNeural"],
    Lang.PS: ["ps-AF-LatifaNeural", "ps-AF-GulNawazNeural"],
    Lang.EN: ["en-US-JennyNeural", "en-GB-SoniaNeural"],
}
ALL_PREFERRED: List[str] = [v for voices in PREFERRED_VOICES.values() for v in voices]

_available_voices: set[str] = set()
_voice_check_done = False
_audio_cache: Dict[str, bytes] = {}
_CACHE_LIMIT = 64  # entries; demo-scale, keeps memory bounded


class TTSError(Exception):
    """Raised when speech synthesis fails; the frontend then falls back
    to the browser's own speechSynthesis."""


async def init_voices() -> None:
    """Populate the available-voice set from edge-tts (called at startup).

    Never raises: if the listing fails (e.g. no network at boot), the app
    still starts and synthesis is attempted optimistically per request.
    """
    global _voice_check_done
    try:
        voices = await asyncio.wait_for(edge_tts.list_voices(), timeout=20)
        _available_voices.update(v["ShortName"] for v in voices)
    except Exception:
        pass
    _voice_check_done = True


def voices_available() -> List[str]:
    """Return which of the preferred voices are confirmed to exist."""
    if not _voice_check_done:
        return []
    return [v for v in ALL_PREFERRED if v in _available_voices]


def pick_voice(lang: Lang) -> str:
    """Choose the best voice for a language, with graceful fallback."""
    for voice in PREFERRED_VOICES[lang]:
        if not _voice_check_done or voice in _available_voices:
            return voice
    # No voice for this language: fall back to English (the frontend is
    # told via /api/health and will announce this in spoken English).
    for voice in PREFERRED_VOICES[Lang.EN]:
        if not _voice_check_done or voice in _available_voices:
            return voice
    return PREFERRED_VOICES[Lang.EN][0]


def _cache_key(text: str, voice: str) -> str:
    return hashlib.sha256(f"{voice}\n{text}".encode("utf-8")).hexdigest()


async def synthesize(text: str, lang: Lang, timeout: float = 15.0) -> bytes:
    """Synthesize speech for ``text`` and return MP3 bytes.

    Raises:
        TTSError: if edge-tts produces no audio within the timeout.
    """
    voice = pick_voice(lang)
    key = _cache_key(text, voice)
    cached = _audio_cache.get(key)
    if cached is not None:
        return cached

    # Respect a standard HTTPS_PROXY when one is configured (e.g. behind
    # a corporate / sandbox egress proxy); None on a normal host.
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or None

    async def _run() -> bytes:
        communicate = edge_tts.Communicate(text=text, voice=voice, proxy=proxy)
        chunks: list[bytes] = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                chunks.append(chunk["data"])
        return b"".join(chunks)

    try:
        audio = await asyncio.wait_for(_run(), timeout=timeout)
        if not audio:
            raise TTSError("Speech synthesis returned no audio")
    except Exception:
        audio = b""
        # Fallback 1: the Edge-voice relay (same voices, all languages).
        try:
            audio = await asyncio.wait_for(_relay_tts(text, lang), timeout=timeout + 15)
        except Exception:
            audio = b""
        # Fallback 2: Google Translate TTS (no Pashto voice there).
        if not audio:
            try:
                audio = await asyncio.wait_for(_google_tts(text, lang), timeout=timeout)
            except Exception as exc:
                raise TTSError(f"Speech synthesis failed: {type(exc).__name__}") from exc
        if not audio:
            raise TTSError("Speech synthesis returned no audio")
    if len(_audio_cache) >= _CACHE_LIMIT:
        _audio_cache.pop(next(iter(_audio_cache)))  # evict oldest
    _audio_cache[key] = audio
    return audio


# Relay voice ids for the same Edge voices (verified against the
# relay's voice catalog): Uzma (ur-PK), Latifa (ps-AF), Jenny (en-US).
_RELAY_VOICE = {Lang.UR: "voice-311", Lang.PS: "voice-215", Lang.EN: "voice-119"}
_RELAY_URL = "https://freeapi.pro/api/tts"


async def _relay_tts(text: str, lang: Lang) -> bytes:
    """Synthesize via the Edge-voice relay and concatenate MP3 parts."""
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or None
    audio = b""
    async with httpx.AsyncClient(
        timeout=20.0, follow_redirects=True, trust_env=False, proxy=proxy
    ) as client:
        for chunk in _chunks(text, limit=350):
            resp = await client.post(
                _RELAY_URL, json={"text": chunk, "voice": _RELAY_VOICE[lang]}
            )
            if resp.status_code != 200 or not resp.content:
                raise TTSError(f"Relay TTS returned status {resp.status_code}")
            audio += resp.content
    return audio


_GOOGLE_TL = {Lang.UR: "ur", Lang.PS: "ps", Lang.EN: "en"}


def _chunks(text: str, limit: int = 180) -> List[str]:
    """Split text into <=limit-char pieces on sentence boundaries."""
    parts = [p.strip() for p in re.split(r"(?<=[.!?۔؟])\s+", text) if p.strip()]
    out: List[str] = []
    current = ""
    for part in parts or [text]:
        while len(part) > limit:  # very long sentence: hard-split
            out.append(part[:limit])
            part = part[limit:]
        if len(current) + len(part) + 1 <= limit:
            current = (current + " " + part).strip()
        else:
            if current:
                out.append(current)
            current = part
    if current:
        out.append(current)
    return out


async def _google_tts(text: str, lang: Lang) -> bytes:
    """Synthesize via Google Translate TTS and concatenate the MP3 parts.

    MP3 frames from the same encoder settings concatenate cleanly, which
    the sibling Book Audio App already relies on in production.
    """
    tl = _GOOGLE_TL[lang]
    headers = {"User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36"}
    audio = b""
    # Explicit proxy + trust_env=False: some sandboxes export no_proxy
    # lists that httpx's env parsing chokes on; the explicit proxy (when
    # configured) is the route out, and on normal hosts there is none.
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or None
    async with httpx.AsyncClient(
        timeout=12.0, follow_redirects=True, trust_env=False, proxy=proxy
    ) as client:
        for chunk in _chunks(text):
            resp = await client.get(
                "https://translate.google.com/translate_tts",
                params={"ie": "UTF-8", "q": chunk, "tl": tl, "client": "tw-ob"},
                headers=headers,
            )
            if resp.status_code != 200 or not resp.content:
                raise TTSError(f"Fallback TTS returned status {resp.status_code}")
            audio += resp.content
    return audio

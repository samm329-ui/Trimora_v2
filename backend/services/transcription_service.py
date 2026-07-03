from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from backend.config.settings import settings

logger = logging.getLogger(__name__)

try:
    from groq import Groq

    _HAVE_GROQ = True
except ImportError:
    _HAVE_GROQ = False

try:
    from google import genai as google_genai

    _HAVE_GEMINI = True
except ImportError:
    _HAVE_GEMINI = False


@dataclass
class TranscriptionResult:
    chunk_id: str
    start: float
    end: float
    text: str
    confidence: float = 0.5


# ---------------------------------------------------------------------------
# Groq
# ---------------------------------------------------------------------------

def _build_groq_client() -> Groq | None:
    if not _HAVE_GROQ:
        return None
    key = settings.groq_api_key or os.getenv("GROQ_API_KEY", "")
    if not key:
        return None
    return Groq(api_key=key)


def _groq_transcribe(client: Groq, chunk_path: Path, chunk_id: str, start: float, end: float) -> TranscriptionResult:
    with open(chunk_path, "rb") as audio:
        translation = client.audio.transcriptions.create(
            model="whisper-large-v3-turbo",
            file=audio,
            response_format="verbose_json",
        )
    segments = getattr(translation, "segments", [])
    confidence = 0.0
    if segments:
        confidence = sum(s.get("confidence", 0.0) for s in segments) / len(segments)
    return TranscriptionResult(
        chunk_id=chunk_id,
        start=start,
        end=end,
        text=translation.text or "",
        confidence=round(confidence, 4),
    )


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------

def _build_gemini_client() -> google_genai.Client | None:
    if not _HAVE_GEMINI:
        return None
    key = settings.gemini_api_key or os.getenv("GEMINI_API_KEY", "")
    if not key:
        return None
    return google_genai.Client(api_key=key)


def _gemini_transcribe(client: google_genai.Client, chunk_path: Path, chunk_id: str, start: float, end: float) -> TranscriptionResult:
    prompt = (
        "Transcribe this audio clip exactly. Return only the spoken text, no timestamps, no commentary."
    )
    with open(chunk_path, "rb") as f:
        audio_bytes = f.read()
    suffix = chunk_path.suffix or ".opus"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                google_genai.types.Part.from_bytes(data=audio_bytes, mime_type="audio/ogg"),
                prompt,
            ],
        )
        text = response.text or ""
        text = text.strip()
    finally:
        os.unlink(tmp_path)
    return TranscriptionResult(
        chunk_id=chunk_id,
        start=start,
        end=end,
        text=text,
        confidence=0.65,
    )


# ---------------------------------------------------------------------------
# Fallback (stub)
# ---------------------------------------------------------------------------

def _stub_transcribe(chunk_id: str, start: float, end: float) -> TranscriptionResult:
    duration = max(end - start, 1.0)
    text = (
        f"This is a generated transcript placeholder for {chunk_id}. "
        f"It covers a span of {duration:.1f} seconds and keeps the pipeline runnable."
    )
    return TranscriptionResult(chunk_id=chunk_id, start=start, end=end, text=text, confidence=0.62)


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

class _RateLimiter:
    """Token-bucket rate limiter with enforced minimum delay between requests."""

    def __init__(self, max_requests: int, window_seconds: float):
        self._min_delay = window_seconds / max_requests
        self._last_request: float = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request
            if elapsed < self._min_delay:
                wait = self._min_delay - elapsed
                logger.debug(f"Rate limiter: waiting {wait:.1f}s")
                await asyncio.sleep(wait)
            self._last_request = time.monotonic()


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------

class TranscriptionService:
    def __init__(self) -> None:
        self._groq: Groq | None = None
        self._gemini: google_genai.Client | None = None
        self._rate_limiter: _RateLimiter | None = None
        provider = settings.transcription_provider

        if provider == "groq":
            self._groq = _build_groq_client()
            if self._groq is None:
                logger.warning("GROQ_API_KEY not set, falling back to Gemini")
                self._gemini = _build_gemini_client()
        elif provider == "gemini":
            self._gemini = _build_gemini_client()
            if self._gemini is None:
                logger.warning("GEMINI_API_KEY not set, falling back to Groq")
                self._groq = _build_groq_client()

        # Rate limit Groq: 15 req/min with 4s minimum gap (free tier is 20/min)
        if self._groq is not None:
            self._rate_limiter = _RateLimiter(max_requests=15, window_seconds=60)

    async def transcribe_chunk(self, chunk_id: str, chunk_path: Path, start: float, end: float) -> TranscriptionResult:
        if self._rate_limiter is not None:
            await self._rate_limiter.acquire()
        return await asyncio.to_thread(self._transcribe_sync, chunk_id, chunk_path, start, end)

    def _transcribe_sync(self, chunk_id: str, chunk_path: Path, start: float, end: float) -> TranscriptionResult:
        if self._groq is not None:
            return _groq_transcribe(self._groq, chunk_path, chunk_id, start, end)
        if self._gemini is not None:
            return _gemini_transcribe(self._gemini, chunk_path, chunk_id, start, end)
        return _stub_transcribe(chunk_id, start, end)

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import threading
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
# Groq round-robin helpers
# ---------------------------------------------------------------------------

@dataclass
class _GroqEntry:
    """A Groq client paired with its own rate limiter."""
    client: Groq
    rate_limiter: "_RateLimiter"


def _build_groq_entries() -> list[_GroqEntry]:
    """Build one Groq client per API key, each with its own rate limiter."""
    if not _HAVE_GROQ:
        return []

    keys: list[str] = []
    if settings.groq_api_key:
        keys.append(settings.groq_api_key)
    for key in settings.groq_api_keys:
        if key not in keys:
            keys.append(key)

    if not keys:
        return []

    entries = []
    for key in keys:
        client = Groq(api_key=key)
        # 15 req/min per key (free tier allows 20/min, leave headroom)
        limiter = _RateLimiter(max_requests=15, window_seconds=60)
        entries.append(_GroqEntry(client=client, rate_limiter=limiter))

    logger.info("Groq transcription: %d API key(s) configured for round-robin", len(entries))
    return entries


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
        self._groq_entries: list[_GroqEntry] = []
        self._groq_index: int = 0
        self._groq_lock: threading.Lock = threading.Lock()
        self._gemini: google_genai.Client | None = None
        provider = settings.transcription_provider

        if provider == "groq":
            self._groq_entries = _build_groq_entries()
            if not self._groq_entries:
                logger.warning("No GROQ_API_KEY(s) set, falling back to Gemini")
                self._gemini = _build_gemini_client()
        elif provider == "gemini":
            self._gemini = _build_gemini_client()
            if self._gemini is None:
                logger.warning("GEMINI_API_KEY not set, falling back to Groq")
                self._groq_entries = _build_groq_entries()

    def _next_groq_entry(self) -> _GroqEntry | None:
        """Thread-safe round-robin selection across Groq API keys."""
        if not self._groq_entries:
            return None
        with self._groq_lock:
            entry = self._groq_entries[self._groq_index]
            self._groq_index = (self._groq_index + 1) % len(self._groq_entries)
        return entry

    async def transcribe_chunk(self, chunk_id: str, chunk_path: Path, start: float, end: float) -> TranscriptionResult:
        entry = self._next_groq_entry()
        if entry is not None:
            await entry.rate_limiter.acquire()
            return await asyncio.to_thread(
                _groq_transcribe, entry.client, chunk_path, chunk_id, start, end
            )
        if self._gemini is not None:
            return await asyncio.to_thread(
                _gemini_transcribe, self._gemini, chunk_path, chunk_id, start, end
            )
        return await asyncio.to_thread(_stub_transcribe, chunk_id, start, end)

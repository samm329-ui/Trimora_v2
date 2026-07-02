from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.models.transcript import TranscriptChunk


@dataclass
class TranscriptionResult:
    chunk_id: str
    start: float
    end: float
    text: str
    confidence: float = 0.5


class TranscriptionService:
    async def transcribe_chunk(self, chunk_id: str, chunk_path: Path, start: float, end: float) -> TranscriptionResult:
        # Replace with a real transcription provider adapter when available.
        duration = max(end - start, 1.0)
        text = (
            f"This is a generated transcript placeholder for {chunk_id}. "
            f"It covers a span of {duration:.1f} seconds and keeps the pipeline runnable."
        )
        return TranscriptionResult(chunk_id=chunk_id, start=start, end=end, text=text, confidence=0.62)

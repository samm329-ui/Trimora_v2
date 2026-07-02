from __future__ import annotations

from pydantic import BaseModel


class TranscriptChunk(BaseModel):
    chunk_id: str
    start: float
    end: float
    text: str
    confidence: float = 0.0


class TranscriptDocument(BaseModel):
    job_id: str
    chunks: list[TranscriptChunk]
    merged_text: str

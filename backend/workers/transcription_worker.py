from __future__ import annotations

from pathlib import Path

from backend.services.transcription_service import TranscriptionService


class TranscriptionWorker:
    def __init__(self, service: TranscriptionService):
        self.service = service

    async def process(self, chunk_id: str, chunk_path: Path, start: float, end: float):
        return await self.service.transcribe_chunk(chunk_id, chunk_path, start, end)

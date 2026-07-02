from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class SegmentFeatures(BaseModel):
    segment_id: str
    audio_intensity: float = 0.0
    text_density: float = 0.0
    structure_score: float = 0.0
    pattern_score: float = 0.0
    total_score: float = 0.0
    audio_energy: Optional[float] = None
    audio_energy_source: str = "text_heuristic"
    transcription_confidence: Optional[float] = None
    extras: dict[str, float] = Field(default_factory=dict)

    @property
    def non_fallback_count(self) -> int:
        count = 0
        if self.audio_energy_source == "real":
            count += 1
        if self.transcription_confidence is not None and self.transcription_confidence > 0.8:
            count += 1
        return count

    @property
    def duration_seconds(self) -> float:
        return self.extras.get("duration_seconds", 0.0)

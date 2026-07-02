from __future__ import annotations

from pydantic import BaseModel, Field


class LearningEntry(BaseModel):
    job_id: str
    clip_id: str | None = None
    accepted: bool = False
    reason: str = ""
    signals: dict[str, float] = Field(default_factory=dict)


class AnalyticsSummary(BaseModel):
    processing_time_seconds: float = 0.0
    number_of_chunks: int = 0
    number_of_candidates: int = 0
    number_of_final_clips: int = 0
    worker_utilization: float = 0.0
    failure_points: list[str] = Field(default_factory=list)
    quality_notes: list[str] = Field(default_factory=list)

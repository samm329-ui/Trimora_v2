from __future__ import annotations

from pydantic import BaseModel, Field


class StoryBlueprint(BaseModel):
    blueprint_id: str
    story_id: str
    story_name: str
    validated_story_summary: str
    segment_ids: list[str]
    start_time: float
    end_time: float
    target_duration: float
    story_arc: dict[str, str]
    opening_segment: str = ""
    ending_segment: str = ""
    cut_timestamps: list[float] = Field(default_factory=list)
    transition_points: list[float] = Field(default_factory=list)
    cut_confidence: float = 0.5
    blueprint_confidence: float = 0.0
    blueprint_intent: str = ""
    blueprint_signature: str = ""
    notes: str = ""
    rejection_reason: str = ""
    rejection_detail: str = ""

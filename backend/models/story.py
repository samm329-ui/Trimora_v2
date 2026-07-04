from __future__ import annotations

from pydantic import BaseModel, Field

from backend.models.semantic import SegmentRelationship


class StoryCandidate(BaseModel):
    candidate_id: str
    segment_ids: list[str]
    story_name: str
    llm_story_summary: str = ""
    main_message: str = ""
    audience: str = ""
    content_category: str = ""
    difficulty: str = ""
    start_confidence: float = 0.5
    end_confidence: float = 0.5
    boundary_confidence: float = 0.5
    ambiguous_segment_ids: list[str] = Field(default_factory=list)
    verified: bool = False
    verification_issues: list[str] = Field(default_factory=list)


class Story(BaseModel):
    story_id: str
    story_name: str
    version: int = 1
    parent_story_id: str = ""
    llm_story_summary: str = ""
    validated_story_summary: str = ""
    main_message: str = ""
    audience: str = ""
    content_category: str = ""
    difficulty: str = ""
    segment_ids: list[str]
    ambiguous_segment_ids: list[str] = Field(default_factory=list)
    topic: str = ""
    subtopic: str = ""
    story_quality_score: float = 0.0
    completeness: float = 0.0
    coherence: float = 0.0
    hook_quality: float = 0.0
    ending_quality: float = 0.0
    continuity: float = 0.0
    emotional_arc: float = 0.0
    quality_explanation: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    duration: float = 0.0
    story_priority: int = 0
    internal_relationships: list[SegmentRelationship] = Field(default_factory=list)
    segment_count: int = 0
    confidence_score: float = 0.5
    validated: bool = False
    rejection_reason: str = ""
    rejection_detail: str = ""
    repair_actions: list[str] = Field(default_factory=list)


class CoverageCategory(BaseModel):
    segment_id: str
    category: str
    story_ids: list[str] = Field(default_factory=list)


class StoryCoverage(BaseModel):
    total_segments: int = 0
    covered_segments: int = 0
    coverage_score: float = 0.0
    fully_covered: int = 0
    partially_covered: int = 0
    unused: int = 0
    unused_segments: list[str] = Field(default_factory=list)
    unused_duration: float = 0.0
    unused_stories: int = 0
    potential_additional_shorts: int = 0


class StoryCollection(BaseModel):
    job_id: str
    candidates: list[StoryCandidate] = Field(default_factory=list)
    stories: list[Story]
    rejected_stories: list[Story]
    coverage: StoryCoverage

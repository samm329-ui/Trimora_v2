from __future__ import annotations

from pydantic import BaseModel, Field


class SegmentAnnotation(BaseModel):
    segment_id: str
    story_id: str = ""
    topic: str = ""
    subtopic: str = ""
    story_role: str = "body"
    intent: str = "explain"
    speaker_intent: str = ""
    emotion: str = "neutral"
    emotion_intensity: float = 0.5
    importance_score: float = 0.5
    hook_strength: float = 0.0
    ending_strength: float = 0.0
    curiosity_score: float = 0.0
    information_density: float = 0.0
    standalone_score: float = 0.5
    completeness_score: float = 0.5
    context_dependency: str = "low"
    previous_segment_dependency: str = ""
    next_segment_expectation: str = ""
    topic_transition: bool = False
    key_entities: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    semantic_embedding: list[float] = Field(default_factory=list)
    confidence_score: float = 0.5


class SegmentRelationship(BaseModel):
    source_id: str
    target_id: str
    relation_type: str
    confidence: float = 0.5
    reason: str = ""


class LLMStoryBoundary(BaseModel):
    block_ids: list[int] = Field(default_factory=list)
    boundary_segments: list[str]
    story_summary: str
    suggested_name: str
    start_confidence: float = 0.5
    end_confidence: float = 0.5
    boundary_confidence: float = 0.5
    structural_confidence: float = 0.5
    semantic_confidence: float = 0.5
    ambiguous_segments: list[str] = Field(default_factory=list)


class SegmentAnnotations(BaseModel):
    job_id: str
    annotations: list[SegmentAnnotation]
    relationships: list[SegmentRelationship]
    llm_story_boundaries: list[LLMStoryBoundary] = Field(default_factory=list)

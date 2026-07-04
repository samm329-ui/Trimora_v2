from __future__ import annotations

from pydantic import BaseModel, Field


class TopicBlock(BaseModel):
    segments: list  # list[AtomicSegment]
    start: float
    end: float
    original_block_index: int
    structural_confidence: float = 1.0
    synopsis: str = ""
    representative_excerpt: str = ""
    embedding: list[float] = Field(default_factory=list)


class PriorityBlock(BaseModel):
    block_id: int
    priority: str
    score: float


class PriorityQueue(BaseModel):
    blocks: list[PriorityBlock]
    timeline_order: list[int]


class StoryBoundary(BaseModel):
    block_ids: list[int]
    segment_ids: list[str]
    story_summary: str
    suggested_name: str
    start_confidence: float = 0.5
    end_confidence: float = 0.5
    structural_confidence: float = 0.5
    semantic_confidence: float = 0.5
    ambiguous_segments: list[str] = Field(default_factory=list)

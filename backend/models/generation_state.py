from __future__ import annotations

from pydantic import BaseModel, Field


class SegmentUsage(BaseModel):
    segment_id: str
    usage_count: int = 0
    blueprint_ids: list[str] = Field(default_factory=list)


class DuplicateRejection(BaseModel):
    blueprint_id: str
    reason: str
    detail: str


class RepairRecord(BaseModel):
    candidate_id: str
    original_issues: list[str]
    repair_actions: list[str]
    success: bool


class PipelineTiming(BaseModel):
    semantic_annotation_ms: float = 0.0
    story_reasoning_ms: float = 0.0
    story_verification_ms: float = 0.0
    story_repair_ms: float = 0.0
    story_validation_ms: float = 0.0
    coverage_analysis_ms: float = 0.0
    blueprint_generation_ms: float = 0.0
    total_semantic_ms: float = 0.0


class RepairStats(BaseModel):
    total_candidates: int = 0
    candidates_repaired: int = 0
    candidates_rejected: int = 0
    repair_success_rate: float = 0.0


class BlueprintGenerationState(BaseModel):
    job_id: str
    segment_usage: dict[str, SegmentUsage] = Field(default_factory=dict)
    total_blueprints_generated: int = 0
    blueprints_rejected_duplicates: int = 0
    duplicate_rejections: list[DuplicateRejection] = Field(default_factory=list)
    repair_records: list[RepairRecord] = Field(default_factory=list)
    repair_stats: RepairStats = Field(default_factory=RepairStats)
    pipeline_timing: PipelineTiming = Field(default_factory=PipelineTiming)

# backend/models/evaluation.py

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class EvaluationLifecycle(Enum):
    GENERATED = "generated"
    EDITED = "edited"
    UPLOADED = "uploaded"
    SEVEN_DAY_METRICS = "7d_metrics"
    THIRTY_DAY_METRICS = "30d_metrics"


class RejectionType(Enum):
    PIPELINE_DEDUP = "pipeline_dedup"
    PIPELINE_OBJECTIVE = "pipeline_objective"
    PIPELINE_PORTFOLIO = "pipeline_portfolio"
    HUMAN_CREATOR = "human_creator"
    HUMAN_PERFORMANCE = "human_performance"


@dataclass(frozen=True)
class GroundTruth:
    generated_clip_id: str = ""
    final_clip_path: str = ""
    creator_rating: Optional[float] = None
    edit_distance: Optional[float] = None
    watch_time: Optional[float] = None
    completion_rate: Optional[float] = None
    engagement: Optional[dict] = None


@dataclass(frozen=True)
class EvaluationRecord:
    record_id: str = ""
    job_id: str = ""
    clip_id: str = ""
    candidate_id: str = ""
    selected: bool = False
    rank: int = 0
    portfolio_position: int = 0
    lifecycle: EvaluationLifecycle = EvaluationLifecycle.GENERATED
    rejection_type: Optional[RejectionType] = None
    rejection_reason: str = ""
    rejection_stage: str = ""
    rejection_scores: dict = field(default_factory=dict)
    objective_scores: dict = field(default_factory=dict)
    overall_score: float = 0.0
    pipeline_version: str = ""
    objective_registry_version: str = ""
    strategy_registry_version: str = ""
    artifact_hashes: dict = field(default_factory=dict)
    config_snapshot: dict = field(default_factory=dict)
    ground_truth: Optional[GroundTruth] = None

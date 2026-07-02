from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Candidate:
    id: str
    hook_text: str
    body_text: str
    ending_text: str
    hook_start: float
    hook_end: float
    body_start: float
    body_end: float
    ending_start: float
    ending_end: float
    duration: float = 0.0
    raw_score: float = 0.0
    flow_score: float = 0.0
    eliminated_at: Optional[str] = None
    elimination_reasons: list[str] = field(default_factory=list)

    def __post_init__(self):
        if self.duration == 0.0:
            self.duration = (self.hook_end - self.hook_start) + (self.body_end - self.body_start) + (self.ending_end - self.ending_start)


@dataclass
class RankedClip:
    candidate: Candidate
    final_score: float = 0.0
    overall_confidence: float = 0.0
    rank: int = 0
    stage_scores: dict[str, float] = field(default_factory=dict)
    stage_confidences: dict[str, float] = field(default_factory=dict)
    hook_quality_score: float = 0.0
    hook_quality_confidence: float = 0.0
    narrative_score: float = 0.0
    narrative_confidence: float = 0.0
    context_score: float = 0.0
    context_confidence: float = 0.0
    density_score: float = 0.0
    density_confidence: float = 0.0
    retention_score: float = 0.0
    retention_confidence: float = 0.0
    novelty_score: float = 0.0
    novelty_confidence: float = 0.0
    explanation: str = ""


@dataclass
class RankingResult:
    job_id: str = ""
    total_candidates: int = 0
    after_pruning: int = 0
    after_hard_constraints: int = 0
    after_global_optimization: int = 0
    final_ranked: int = 0
    pruning_stats: dict = field(default_factory=dict)
    ranked_clips: list[RankedClip] = field(default_factory=list)
    eliminated_clips: list[dict] = field(default_factory=list)
    ranking_config: dict = field(default_factory=dict)

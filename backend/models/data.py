# backend/models/data.py

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class TranscriptData:
    segments: list = field(default_factory=list)
    merged_text: str = ""
    word_count: int = 0
    duration: float = 0.0


@dataclass(frozen=True)
class SignalData:
    segments: list = field(default_factory=list)
    audio_signals: list = field(default_factory=list)
    text_signals: list = field(default_factory=list)
    signal_count: int = 0


@dataclass(frozen=True)
class EvidenceData:
    evidence: list = field(default_factory=list)
    evidence_count: int = 0
    evidence_types: dict = field(default_factory=dict)


@dataclass(frozen=True)
class GraphData:
    nodes: list = field(default_factory=list)
    edges: list = field(default_factory=list)
    node_count: int = 0
    edge_count: int = 0
    knowledge_version: int = 0


@dataclass(frozen=True)
class CandidatesData:
    candidates: list = field(default_factory=list)
    candidate_count: int = 0
    strategies_used: list = field(default_factory=list)
    deduplication_result: Optional[dict] = None


@dataclass(frozen=True)
class ScoresData:
    scored_candidates: list = field(default_factory=list)
    objective_scores: dict = field(default_factory=dict)
    score_distribution: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PortfolioData:
    portfolio: dict = field(default_factory=dict)
    selected_count: int = 0
    rejected_count: int = 0
    total_score: float = 0.0
    diversity_score: float = 0.0


@dataclass(frozen=True)
class EvaluationData:
    records: list = field(default_factory=list)
    pipeline_version: str = ""
    objective_registry_version: str = ""
    strategy_registry_version: str = ""
    artifact_hashes: dict = field(default_factory=dict)


@dataclass(frozen=True)
class GroundTruthData:
    generated_clip_id: str = ""
    final_clip_path: str = ""
    creator_rating: Optional[float] = None
    edit_distance: Optional[float] = None
    watch_time: Optional[float] = None
    completion_rate: Optional[float] = None
    engagement: Optional[dict] = None

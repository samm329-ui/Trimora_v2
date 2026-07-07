# backend/models/clip.py

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class ClipCandidate:
    id: str = ""
    strategy: str = ""
    event_ids: list = field(default_factory=list)
    start: float = 0.0
    end: float = 0.0
    duration: float = 0.0
    hook_text: str = ""
    body_text: str = ""
    ending_text: str = ""
    overall_score: float = 0.0
    objective_scores: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PortfolioClip:
    candidate_id: str = ""
    rank: int = 0
    overall_score: float = 0.0
    objective_scores: dict = field(default_factory=dict)
    strategy: str = ""
    start: float = 0.0
    end: float = 0.0
    duration: float = 0.0


@dataclass(frozen=True)
class Portfolio:
    clips: list = field(default_factory=list)
    total_score: float = 0.0
    diversity_score: float = 0.0
    selected_count: int = 0
    rejected_count: int = 0

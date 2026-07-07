from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from pydantic import BaseModel, Field


class ClipCandidate(BaseModel):
    id: str
    title: str
    hook_start: float
    hook_end: float
    body_start: float
    body_end: float
    ending_start: float
    ending_end: float
    duration: float
    hook_score: float
    body_score: float
    ending_score: float
    flow_score: float
    total_score: float
    status: str = "candidate"
    transcript_snippet: str = ""
    hook_text: str = ""
    body_text: str = ""
    ending_text: str = ""


class PreviewManifest(BaseModel):
    job_id: str
    clips: list[ClipCandidate] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# V10.1 Clip Models (frozen dataclasses)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ClipV101:
    """V10.1 clip candidate — immutable."""
    id: str = ""
    strategy: str = ""
    start: float = 0.0
    end: float = 0.0
    duration: float = 0.0
    hook_text: str = ""
    body_text: str = ""
    ending_text: str = ""
    event_ids: list = field(default_factory=list)
    overall_score: float = 0.0
    objective_scores: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PortfolioClip:
    """A clip in the portfolio — immutable."""
    id: str = ""
    candidate_id: str = ""
    rank: int = 0
    overall_score: float = 0.0
    diversity_score: float = 0.0
    objective_scores: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Portfolio:
    """Portfolio of selected clips — immutable."""
    clips: list = field(default_factory=list)
    total_score: float = 0.0
    diversity_score: float = 0.0
    selected_count: int = 0
    rejected_count: int = 0
